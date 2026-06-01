"""파이프라인 DB 색인 모듈.

파이프라인 각 Stage의 결과를 DB에 저장하는 함수 모음.
  - save_chunks: document_chunks 삽입 (quality_score 즉시 계산)
  - save_embeddings: chunk_embeddings 삽입
  - map_chunk_topics: chunk_topics (M:N) 삽입 — ON CONFLICT DO NOTHING
  - save_dump_questions: questions + choices + answer_explanations 삽입
  - reindex_vector: IVFFlat REINDEX (autocommit 연결 사용)

docs/05-rag-pipeline.md Stage 3~5 기준 구현.
NOTE: save_chunks에서 quality_score를 즉시 계산해 저장한다.
      docs Stage 3A 다이어그램의 quality_score=null → Stage 5 업데이트 흐름과
      다르나 별도 UPDATE 없이 단일 INSERT로 처리해 구현 단순화.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import get_settings
from app.models.answer_explanation import AnswerExplanation
from app.models.choice import Choice
from app.models.chunk_embedding import ChunkEmbedding
from app.models.chunk_topic import ChunkTopic
from app.models.document_chunk import DocumentChunk
from app.models.question import Question
from app.pipeline.parser import ParsedQuestion
from app.pipeline.quality import ChunkQualityInput, compute_quality_score, resolve_is_active

logger = logging.getLogger(__name__)

_EMBED_MODEL_NAME = "text-embedding-004"
_EMBED_MODEL_VERSION = "001"


# ──────────────────────────────────────────────
# OFFICIAL_GUIDE 경로 — 청크 저장
# ──────────────────────────────────────────────

async def save_chunks(
    session: AsyncSession,
    chunks: list[dict],
) -> list[dict]:
    """document_chunks 테이블에 청크를 삽입하고 chunk_id를 담은 목록을 반환한다.

    Args:
        session: AsyncSession
        chunks: hierarchical_chunk() 반환값
            [{"chunk_text", "chunk_order", "token_count",
              "section_path", "page_number", "document_version_id"}]

    Returns:
        [{"chunk_id": UUID, "chunk_text": str, "token_count": int,
          "section_path": str, "document_version_id": str}]
    """
    results: list[dict] = []

    for c in chunks:
        quality_input = ChunkQualityInput(
            chunk_text=c["chunk_text"],
            token_count=c["token_count"],
            section_path=c.get("section_path", ""),
        )
        quality_score = compute_quality_score(quality_input)
        is_active = resolve_is_active(quality_score)

        chunk = DocumentChunk(
            document_version_id=uuid.UUID(c["document_version_id"]),
            chunk_text=c["chunk_text"],
            chunk_order=c["chunk_order"],
            token_count=c["token_count"],
            quality_score=quality_score,
            is_active=is_active,
        )
        session.add(chunk)
        await session.flush()  # ID 확보

        results.append({
            "chunk_id": chunk.id,
            "chunk_text": c["chunk_text"],
            "token_count": c["token_count"],
            "section_path": c.get("section_path", ""),
            "document_version_id": c["document_version_id"],
        })

    await session.commit()
    logger.info("save_chunks: %d개 청크 저장 완료", len(results))
    return results


# ──────────────────────────────────────────────
# OFFICIAL_GUIDE 경로 — 임베딩 저장
# ──────────────────────────────────────────────

async def save_embeddings(
    session: AsyncSession,
    chunk_results: list[dict],
    embeddings: list[Optional[list[float]]],
    model_name: str = _EMBED_MODEL_NAME,
    model_version: str = _EMBED_MODEL_VERSION,
) -> int:
    """chunk_embeddings 테이블에 임베딩을 저장한다.

    Args:
        chunk_results: save_chunks() 반환값
        embeddings: embed_chunks() 반환값 (None이면 해당 청크 건너뜀)

    Returns:
        저장 성공 청크 수
    """
    saved = 0
    skipped = 0

    for chunk, embedding in zip(chunk_results, embeddings):
        if embedding is None:
            skipped += 1
            continue
        session.add(ChunkEmbedding(
            chunk_id=chunk["chunk_id"],
            embedding=embedding,
            model_name=model_name,
            model_version=model_version,
        ))
        saved += 1

    await session.commit()
    if skipped:
        logger.warning("save_embeddings: %d개 임베딩 실패 건너뜀", skipped)
    logger.info("save_embeddings: %d개 임베딩 저장 완료", saved)
    return saved


# ──────────────────────────────────────────────
# OFFICIAL_GUIDE 경로 — 토픽 매핑
# ──────────────────────────────────────────────

async def map_chunk_topics(
    session: AsyncSession,
    chunk_id: uuid.UUID,
    chunk_text: str,
    certification_id: uuid.UUID,
) -> list[uuid.UUID]:
    """청크 텍스트 키워드 매칭으로 chunk_topics M:N 관계를 저장한다.

    topics.name의 첫 2단어가 chunk_text에 모두 포함되면 매핑.
    ON CONFLICT DO NOTHING으로 UNIQUE(chunk_id, topic_id) 충돌 안전 처리.
    (docs/05-rag-pipeline.md 섹션 6-2: Wave 3 키워드 매칭 초기 구현)
    """
    stmt = text("""
        SELECT t.id, t.name
        FROM topics t
        JOIN exam_domains ed ON t.exam_domain_id = ed.id
        WHERE ed.certification_id = :cert_id
          AND t.is_deleted = false
    """)
    rows = await session.execute(stmt, {"cert_id": str(certification_id)})
    topics = rows.fetchall()

    text_lower = chunk_text.lower()
    matched: list[uuid.UUID] = []

    for row in topics:
        topic_id, topic_name = row
        keywords = topic_name.lower().split()
        if not keywords:
            continue
        if all(kw in text_lower for kw in keywords[:2]):
            matched.append(uuid.UUID(str(topic_id)))

    if matched:
        # ON CONFLICT DO NOTHING: UNIQUE(chunk_id, topic_id) 중복 삽입 안전 처리
        insert_stmt = (
            pg_insert(ChunkTopic)
            .values([{"chunk_id": chunk_id, "topic_id": tid} for tid in matched])
            .on_conflict_do_nothing(index_elements=["chunk_id", "topic_id"])
        )
        await session.execute(insert_stmt)
        await session.commit()
        logger.debug(
            "map_chunk_topics: chunk_id=%s → %d개 토픽 매핑", chunk_id, len(matched)
        )

    return matched


# ──────────────────────────────────────────────
# DUMP 경로 — 문제 저장
# ──────────────────────────────────────────────

async def save_dump_questions(
    session: AsyncSession,
    certification_id: uuid.UUID,
    questions: list[ParsedQuestion],
    default_topic_id: Optional[uuid.UUID] = None,
) -> int:
    """덤프 파싱 결과를 questions + choices + answer_explanations에 저장한다.

    topic_id가 없으면 해당 certification의 첫 번째 topic을 사용한다.
    (docs/05-rag-pipeline.md 섹션 5-2: 초기 topic 할당, 추후 분류 개선)
    """
    if default_topic_id is None:
        stmt = text("""
            SELECT t.id FROM topics t
            JOIN exam_domains ed ON t.exam_domain_id = ed.id
            WHERE ed.certification_id = :cert_id
              AND t.is_deleted = false
            ORDER BY t.created_at
            LIMIT 1
        """)
        row = (await session.execute(stmt, {"cert_id": str(certification_id)})).fetchone()
        if row is None:
            raise ValueError(
                f"certification_id={certification_id}에 연결된 topic이 없습니다. "
                "exam_domains와 topics를 먼저 생성하세요."
            )
        default_topic_id = uuid.UUID(str(row[0]))

    saved = 0
    for pq in questions:
        question = Question(
            certification_id=certification_id,
            topic_id=default_topic_id,
            source_chunk_id=None,
            question_text=pq.question_text,
            question_type="SINGLE",
            source_type="DUMP",
            difficulty="INTERMEDIATE",
        )
        session.add(question)
        await session.flush()

        for idx, c in enumerate(pq.choices):
            session.add(Choice(
                question_id=question.id,
                choice_text=c["text"],
                choice_label=c["label"],
                is_correct=c["is_correct"],
                order_num=c.get("order_num", idx),
            ))

        if pq.explanation:
            session.add(AnswerExplanation(
                question_id=question.id,
                explanation_text=pq.explanation,
                source_chunk_id=None,
            ))

        saved += 1

    await session.commit()
    logger.info("save_dump_questions: %d개 문제 저장 완료", saved)
    return saved


# ──────────────────────────────────────────────
# IVFFlat 인덱스 REINDEX
# ──────────────────────────────────────────────

async def reindex_vector(session: AsyncSession) -> None:  # noqa: ARG001
    """파이프라인 완료 후 IVFFlat 인덱스 재구성.

    REINDEX INDEX CONCURRENTLY는 트랜잭션 블록 내 실행 불가이므로
    autocommit 모드의 별도 엔진 연결을 사용한다.
    인덱스가 존재하지 않으면 조용히 건너뜀.
    docs/05-rag-pipeline.md 섹션 7-2 참고.
    """
    settings = get_settings()
    engine = create_async_engine(
        settings.async_database_url,
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text("REINDEX INDEX CONCURRENTLY idx_chunk_embeddings_embedding_ivfflat")
            )
        logger.info("reindex_vector: IVFFlat 인덱스 재구성 완료")
    except Exception as exc:
        logger.warning("reindex_vector: 인덱스 재구성 건너뜀 — %s", exc)
    finally:
        await engine.dispose()
