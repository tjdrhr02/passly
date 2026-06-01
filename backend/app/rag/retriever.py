"""RAG 하이브리드 검색 모듈.

pgvector 코사인 유사도 + PostgreSQL FTS를 RRF로 결합.
docs/05-rag-pipeline.md 섹션 7 참고.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import embed_texts

logger = logging.getLogger(__name__)

_RRF_K = 60  # RRF 상수 (표준값)
_TOP_N = 10  # 최종 반환 청크 수


async def hybrid_search(
    db: AsyncSession,
    query: str,
    certification_id: uuid.UUID,
    user_access_level: str = "SHARED",
    top_n: int = _TOP_N,
) -> list[dict[str, Any]]:
    """하이브리드 검색 (pgvector + FTS + RRF).

    Args:
        db: 비동기 DB 세션
        query: 사용자 질문
        certification_id: 검색 대상 자격증 ID
        user_access_level: 사용자 접근 레벨 (PRIVATE | SHARED)
        top_n: 반환할 청크 수

    Returns:
        chunk 딕셔너리 목록 (chunk_id, chunk_text, chunk_summary, rrf_score 포함)
    """
    # 1. 쿼리 임베딩 생성
    try:
        embeddings = await embed_texts([query], task_type="retrieval_query")
        query_embedding = embeddings[0] if embeddings else None
    except Exception as exc:
        logger.error("쿼리 임베딩 실패: %s", exc)
        query_embedding = None

    # 접근 레벨 필터: PRIVATE 사용자는 모든 레벨 접근 가능, SHARED는 SHARED만
    access_levels = ["SHARED"]
    if user_access_level == "PRIVATE":
        access_levels = ["PRIVATE", "SHARED"]

    access_levels_sql = ", ".join(f"'{lvl}'" for lvl in access_levels)

    # 2. FTS 검색
    fts_sql = text(f"""
        SELECT
            dc.id::text AS chunk_id,
            dc.chunk_text,
            dc.chunk_summary,
            ROW_NUMBER() OVER (ORDER BY ts_rank(dc.chunk_tsv, plainto_tsquery('english', :query)) DESC) AS rank
        FROM document_chunks dc
        JOIN document_versions dv ON dv.id = dc.document_version_id
        JOIN learning_documents ld ON ld.id = dv.learning_document_id
        WHERE ld.certification_id = :certification_id
          AND dc.access_level IN ({access_levels_sql})
          AND dc.is_active = true
          AND dv.is_active = true
          AND dc.chunk_tsv @@ plainto_tsquery('english', :query)
        ORDER BY ts_rank(dc.chunk_tsv, plainto_tsquery('english', :query)) DESC
        LIMIT 20
    """)

    fts_rows: dict[str, int] = {}
    try:
        result = await db.execute(fts_sql, {"query": query, "certification_id": certification_id})
        for row in result.mappings():
            fts_rows[row["chunk_id"]] = int(row["rank"])
    except Exception as exc:
        logger.warning("FTS 검색 실패: %s", exc)

    # 3. 벡터 검색 (임베딩이 있을 때만)
    vec_rows: dict[str, int] = {}
    chunk_details: dict[str, dict[str, Any]] = {}

    if query_embedding is not None:
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        vec_sql = text(f"""
            SELECT
                dc.id::text AS chunk_id,
                dc.chunk_text,
                dc.chunk_summary,
                ROW_NUMBER() OVER (ORDER BY ce.embedding <=> :embedding::vector) AS rank
            FROM chunk_embeddings ce
            JOIN document_chunks dc ON dc.id = ce.chunk_id
            JOIN document_versions dv ON dv.id = dc.document_version_id
            JOIN learning_documents ld ON ld.id = dv.learning_document_id
            WHERE ld.certification_id = :certification_id
              AND dc.access_level IN ({access_levels_sql})
              AND dc.is_active = true
              AND dv.is_active = true
            ORDER BY ce.embedding <=> :embedding::vector
            LIMIT 20
        """)
        try:
            result = await db.execute(
                vec_sql,
                {"embedding": embedding_str, "certification_id": certification_id},
            )
            for row in result.mappings():
                cid = row["chunk_id"]
                vec_rows[cid] = int(row["rank"])
                chunk_details[cid] = {
                    "chunk_id": cid,
                    "chunk_text": row["chunk_text"],
                    "chunk_summary": row["chunk_summary"],
                }
        except Exception as exc:
            logger.warning("벡터 검색 실패: %s", exc)

    # FTS 결과에서도 chunk_details 채우기 (벡터 검색이 없을 때 대비)
    if not vec_rows and fts_rows:
        fts_detail_sql = text(f"""
            SELECT
                dc.id::text AS chunk_id,
                dc.chunk_text,
                dc.chunk_summary
            FROM document_chunks dc
            JOIN document_versions dv ON dv.id = dc.document_version_id
            JOIN learning_documents ld ON ld.id = dv.learning_document_id
            WHERE dc.id = ANY(:ids)
              AND ld.certification_id = :certification_id
        """)
        try:
            ids = [uuid.UUID(cid) for cid in fts_rows.keys()]
            result = await db.execute(
                fts_detail_sql,
                {"ids": ids, "certification_id": certification_id},
            )
            for row in result.mappings():
                cid = row["chunk_id"]
                chunk_details[cid] = {
                    "chunk_id": cid,
                    "chunk_text": row["chunk_text"],
                    "chunk_summary": row["chunk_summary"],
                }
        except Exception as exc:
            logger.warning("FTS 상세 조회 실패: %s", exc)

    # 4. RRF 점수 계산
    all_ids = set(fts_rows) | set(vec_rows)
    rrf_scores: list[tuple[str, float]] = []
    for cid in all_ids:
        score = 0.0
        if cid in fts_rows:
            score += 1.0 / (_RRF_K + fts_rows[cid])
        if cid in vec_rows:
            score += 1.0 / (_RRF_K + vec_rows[cid])
        rrf_scores.append((cid, score))

    rrf_scores.sort(key=lambda x: x[1], reverse=True)

    # 5. 결과 조립
    results: list[dict[str, Any]] = []
    for cid, score in rrf_scores[:top_n]:
        detail = chunk_details.get(cid, {})
        results.append({
            "chunk_id": cid,
            "chunk_text": detail.get("chunk_text", ""),
            "chunk_summary": detail.get("chunk_summary"),
            "rrf_score": score,
        })

    return results
