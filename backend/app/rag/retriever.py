"""RAG 검색 모듈.

pgvector 코사인 유사도 + PostgreSQL FTS를 RRF로 결합한 Hybrid Search.
Vector 단독 / Keyword 단독 / Hybrid 세 가지 모드를 unified search() 인터페이스로 제공.

docs/04-vector-schema.md 섹션 3-3, 5-4, 6-4 참고.
docs/05-rag-pipeline.md 섹션 8-3 참고.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import embed_texts

logger = logging.getLogger(__name__)

_RRF_K = 60        # RRF 댐핑 파라미터 (Cormack et al. 2009 권장 기본값)
_TOP_N = 10        # 최종 반환 청크 수
_CANDIDATE_K = 20  # 각 검색 방식에서 수집할 후보 수
_MIN_QUALITY = 0.0  # 최소 품질 점수 (docs/04-vector-schema.md 섹션 3-2)
_DEFAULT_PROBES = 15  # IVFFlat probes — /chat 페이지 권장값 (docs/04-vector-schema.md 섹션 5-4)


async def search(
    db: AsyncSession,
    query: str,
    certification_id: uuid.UUID,
    mode: str = "hybrid",
    user_access_level: str = "SHARED",
    top_n: int = _TOP_N,
    min_quality: float = _MIN_QUALITY,
    probes: int = _DEFAULT_PROBES,
) -> list[dict[str, Any]]:
    """통합 검색 진입점. mode에 따라 적절한 구현으로 디스패치한다.

    Args:
        db: 비동기 DB 세션
        query: 사용자 질문
        certification_id: 검색 대상 자격증 ID
        mode: 검색 모드 — "hybrid" | "vector" | "keyword"
        user_access_level: 사용자 접근 레벨 (PRIVATE | SHARED)
        top_n: 반환할 청크 수
        min_quality: 최소 품질 점수 (이 값 미만 청크는 검색에서 제외)
        probes: IVFFlat probes 파라미터 (vector/hybrid 모드에서 적용)

    Returns:
        chunk 딕셔너리 목록
    """
    if mode == "vector":
        return await vector_search(
            db=db,
            query=query,
            certification_id=certification_id,
            user_access_level=user_access_level,
            top_n=top_n,
            min_quality=min_quality,
            probes=probes,
        )
    elif mode == "keyword":
        return await keyword_search(
            db=db,
            query=query,
            certification_id=certification_id,
            user_access_level=user_access_level,
            top_n=top_n,
            min_quality=min_quality,
        )
    else:
        # 기본값: hybrid
        return await hybrid_search(
            db=db,
            query=query,
            certification_id=certification_id,
            user_access_level=user_access_level,
            top_n=top_n,
            min_quality=min_quality,
            probes=probes,
        )


def _build_access_levels_sql(user_access_level: str) -> list[str]:
    """접근 레벨 목록 반환.

    PRIVATE 사용자는 PRIVATE + SHARED 모두 접근 가능.
    SHARED 사용자는 SHARED만 접근 가능.
    """
    if user_access_level == "PRIVATE":
        return ["PRIVATE", "SHARED"]
    return ["SHARED"]


async def vector_search(
    db: AsyncSession,
    query: str,
    certification_id: uuid.UUID,
    user_access_level: str = "SHARED",
    top_n: int = _TOP_N,
    min_quality: float = _MIN_QUALITY,
    probes: int = _DEFAULT_PROBES,
) -> list[dict[str, Any]]:
    """순수 벡터 검색 (코사인 유사도 기반).

    docs/04-vector-schema.md 섹션 7 패턴 1 참고.
    SET LOCAL ivfflat.probes 실행 후 벡터 검색 수행.

    Args:
        db: 비동기 DB 세션
        query: 사용자 질문
        certification_id: 검색 대상 자격증 ID
        user_access_level: 사용자 접근 레벨 (PRIVATE | SHARED)
        top_n: 반환할 청크 수
        min_quality: 최소 품질 점수
        probes: IVFFlat probes 파라미터

    Returns:
        chunk 딕셔너리 목록 (chunk_id, chunk_text, chunk_summary, cosine_distance 포함)
    """
    # 1. 쿼리 임베딩 생성
    try:
        embeddings = await embed_texts([query], task_type="retrieval_query")
        query_embedding = embeddings[0] if embeddings else None
    except Exception as exc:
        logger.error("쿼리 임베딩 실패 (vector_search): %s", exc)
        query_embedding = None

    if query_embedding is None:
        logger.warning("임베딩 생성 실패로 vector_search 결과 없음.")
        return []

    access_levels = _build_access_levels_sql(user_access_level)
    access_levels_sql = ", ".join(f"'{lvl}'" for lvl in access_levels)
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    # 2. IVFFlat probes 세션 설정 (docs/04-vector-schema.md 섹션 5-4)
    try:
        await db.execute(text(f"SET LOCAL ivfflat.probes = {int(probes)}"))
    except Exception as exc:
        logger.warning("ivfflat.probes 설정 실패: %s", exc)

    # 3. 벡터 검색 — 메타데이터 필터 순서: docs/04-vector-schema.md 섹션 3-3
    # asyncpg에서 :param::vector 구문이 파싱 충돌을 일으켜 embedding 값을 SQL에 직접 삽입한다.
    # embedding 값은 Vertex AI가 반환한 float 배열이므로 injection 위험 없음.
    vec_sql = text(f"""
        SELECT
            dc.id::text AS chunk_id,
            dc.chunk_text,
            dc.chunk_summary,
            dc.quality_score,
            ce.embedding <=> '{embedding_str}'::vector AS cosine_distance
        FROM document_chunks dc
        JOIN document_versions dv ON dv.id = dc.document_version_id
        JOIN learning_documents ld ON ld.id = dv.learning_document_id
        JOIN chunk_embeddings ce ON ce.chunk_id = dc.id
        WHERE dc.is_deleted = false
          AND ld.certification_id = :certification_id
          AND dc.access_level IN ({access_levels_sql})
          AND dc.quality_score >= :min_quality
          AND dv.is_active = true
          AND ce.is_deleted = false
        ORDER BY cosine_distance ASC
        LIMIT :top_n
    """)

    results: list[dict[str, Any]] = []
    try:
        result = await db.execute(
            vec_sql,
            {
                "certification_id": certification_id,
                "min_quality": min_quality,
                "top_n": top_n,
            },
        )
        for row in result.mappings():
            results.append({
                "chunk_id": row["chunk_id"],
                "chunk_text": row["chunk_text"],
                "chunk_summary": row["chunk_summary"],
                "quality_score": row["quality_score"],
                "cosine_distance": float(row["cosine_distance"]),
                "rrf_score": 0.0,  # 단독 벡터 검색 — RRF 미사용
            })
    except Exception as exc:
        logger.error("벡터 검색 실패: %s", exc)

    return results


async def keyword_search(
    db: AsyncSession,
    query: str,
    certification_id: uuid.UUID,
    user_access_level: str = "SHARED",
    top_n: int = _TOP_N,
    min_quality: float = _MIN_QUALITY,
) -> list[dict[str, Any]]:
    """순수 키워드 검색 (PostgreSQL Full-text Search 기반).

    docs/04-vector-schema.md 섹션 4, 6-4 참고.
    ts_rank_cd 기준 내림차순 정렬.

    Args:
        db: 비동기 DB 세션
        query: 사용자 질문
        certification_id: 검색 대상 자격증 ID
        user_access_level: 사용자 접근 레벨 (PRIVATE | SHARED)
        top_n: 반환할 청크 수
        min_quality: 최소 품질 점수

    Returns:
        chunk 딕셔너리 목록 (chunk_id, chunk_text, chunk_summary, fts_rank 포함)
    """
    access_levels = _build_access_levels_sql(user_access_level)
    access_levels_sql = ", ".join(f"'{lvl}'" for lvl in access_levels)

    # 메타데이터 필터 순서: docs/04-vector-schema.md 섹션 3-3
    fts_sql = text(f"""
        SELECT
            dc.id::text AS chunk_id,
            dc.chunk_text,
            dc.chunk_summary,
            dc.quality_score,
            ts_rank_cd(dc.chunk_tsv, plainto_tsquery('english', :query)) AS fts_rank
        FROM document_chunks dc
        JOIN document_versions dv ON dv.id = dc.document_version_id
        JOIN learning_documents ld ON ld.id = dv.learning_document_id
        WHERE dc.is_deleted = false
          AND ld.certification_id = :certification_id
          AND dc.access_level IN ({access_levels_sql})
          AND dc.quality_score >= :min_quality
          AND dv.is_active = true
          AND dc.chunk_tsv @@ plainto_tsquery('english', :query)
        ORDER BY fts_rank DESC
        LIMIT :top_n
    """)

    results: list[dict[str, Any]] = []
    try:
        result = await db.execute(
            fts_sql,
            {
                "query": query,
                "certification_id": certification_id,
                "min_quality": min_quality,
                "top_n": top_n,
            },
        )
        for row in result.mappings():
            results.append({
                "chunk_id": row["chunk_id"],
                "chunk_text": row["chunk_text"],
                "chunk_summary": row["chunk_summary"],
                "quality_score": row["quality_score"],
                "fts_rank": float(row["fts_rank"]),
                "rrf_score": 0.0,  # 단독 키워드 검색 — RRF 미사용
            })
    except Exception as exc:
        logger.error("키워드 검색 실패: %s", exc)

    return results


async def hybrid_search(
    db: AsyncSession,
    query: str,
    certification_id: uuid.UUID,
    user_access_level: str = "SHARED",
    top_n: int = _TOP_N,
    min_quality: float = _MIN_QUALITY,
    probes: int = _DEFAULT_PROBES,
) -> list[dict[str, Any]]:
    """하이브리드 검색 (pgvector + FTS + RRF).

    docs/04-vector-schema.md 섹션 6-4 CTE 구조 참고.
    SET LOCAL ivfflat.probes 실행 후 벡터 + FTS 병렬 수집, RRF로 통합.
    임베딩 생성 실패 시 FTS 단독으로 폴백.

    Args:
        db: 비동기 DB 세션
        query: 사용자 질문
        certification_id: 검색 대상 자격증 ID
        user_access_level: 사용자 접근 레벨 (PRIVATE | SHARED)
        top_n: 반환할 청크 수
        min_quality: 최소 품질 점수 (이 값 미만 청크는 검색에서 제외)
        probes: IVFFlat probes 파라미터 (docs/04-vector-schema.md 섹션 5-4)

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

    access_levels = _build_access_levels_sql(user_access_level)
    access_levels_sql = ", ".join(f"'{lvl}'" for lvl in access_levels)

    # 2. IVFFlat probes 세션 설정 (docs/04-vector-schema.md 섹션 5-4)
    try:
        await db.execute(text(f"SET LOCAL ivfflat.probes = {int(probes)}"))
    except Exception as exc:
        logger.warning("ivfflat.probes 설정 실패: %s", exc)

    # 3. FTS 검색 — 메타데이터 필터 순서: docs/04-vector-schema.md 섹션 3-3
    fts_sql = text(f"""
        SELECT
            dc.id::text AS chunk_id,
            dc.chunk_text,
            dc.chunk_summary,
            dc.quality_score,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(dc.chunk_tsv, plainto_tsquery('english', :query)) DESC
            ) AS rank
        FROM document_chunks dc
        JOIN document_versions dv ON dv.id = dc.document_version_id
        JOIN learning_documents ld ON ld.id = dv.learning_document_id
        WHERE dc.is_deleted = false
          AND ld.certification_id = :certification_id
          AND dc.access_level IN ({access_levels_sql})
          AND dc.quality_score >= :min_quality
          AND dv.is_active = true
          AND dc.chunk_tsv @@ plainto_tsquery('english', :query)
        ORDER BY ts_rank_cd(dc.chunk_tsv, plainto_tsquery('english', :query)) DESC
        LIMIT :candidate_k
    """)

    fts_rows: dict[str, int] = {}
    chunk_details: dict[str, dict[str, Any]] = {}

    try:
        result = await db.execute(
            fts_sql,
            {
                "query": query,
                "certification_id": certification_id,
                "min_quality": min_quality,
                "candidate_k": _CANDIDATE_K,
            },
        )
        for row in result.mappings():
            cid = row["chunk_id"]
            fts_rows[cid] = int(row["rank"])
            chunk_details[cid] = {
                "chunk_id": cid,
                "chunk_text": row["chunk_text"],
                "chunk_summary": row["chunk_summary"],
                "quality_score": row["quality_score"],
            }
    except Exception as exc:
        logger.warning("FTS 검색 실패: %s", exc)

    # 4. 벡터 검색 (임베딩이 있을 때만)
    vec_rows: dict[str, int] = {}

    if query_embedding is not None:
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        # asyncpg에서 :param::vector 구문 파싱 충돌 방지 — embedding 값을 SQL에 직접 삽입
        vec_sql = text(f"""
            SELECT
                dc.id::text AS chunk_id,
                dc.chunk_text,
                dc.chunk_summary,
                dc.quality_score,
                ROW_NUMBER() OVER (
                    ORDER BY ce.embedding <=> '{embedding_str}'::vector ASC
                ) AS rank
            FROM document_chunks dc
            JOIN document_versions dv ON dv.id = dc.document_version_id
            JOIN learning_documents ld ON ld.id = dv.learning_document_id
            JOIN chunk_embeddings ce ON ce.chunk_id = dc.id
            WHERE dc.is_deleted = false
              AND ld.certification_id = :certification_id
              AND dc.access_level IN ({access_levels_sql})
              AND dc.quality_score >= :min_quality
              AND dv.is_active = true
              AND ce.is_deleted = false
            ORDER BY ce.embedding <=> '{embedding_str}'::vector ASC
            LIMIT :candidate_k
        """)
        try:
            result = await db.execute(
                vec_sql,
                {
                    "certification_id": certification_id,
                    "min_quality": min_quality,
                    "candidate_k": _CANDIDATE_K,
                },
            )
            for row in result.mappings():
                cid = row["chunk_id"]
                vec_rows[cid] = int(row["rank"])
                # 벡터 결과로 chunk_details 보완 (FTS에 없던 청크 추가)
                if cid not in chunk_details:
                    chunk_details[cid] = {
                        "chunk_id": cid,
                        "chunk_text": row["chunk_text"],
                        "chunk_summary": row["chunk_summary"],
                        "quality_score": row["quality_score"],
                    }
        except Exception as exc:
            logger.warning("벡터 검색 실패: %s", exc)

    # 5. RRF 점수 계산 (docs/04-vector-schema.md 섹션 6-2)
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

    # 6. 결과 조립
    results: list[dict[str, Any]] = []
    for cid, score in rrf_scores[:top_n]:
        detail = chunk_details.get(cid, {})
        results.append({
            "chunk_id": cid,
            "chunk_text": detail.get("chunk_text", ""),
            "chunk_summary": detail.get("chunk_summary"),
            "quality_score": detail.get("quality_score"),
            "rrf_score": score,
        })

    return results
