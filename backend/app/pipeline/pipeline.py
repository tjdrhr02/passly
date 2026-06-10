"""파이프라인 오케스트레이터.

PDF 처리 파이프라인의 전체 흐름을 조율한다:
  Stage 1: pipeline_runs 상태 → PROCESSING
  Stage 2: PDF 파싱 (extract_text_blocks 또는 parse_dump_pages)
  Stage 3A: 청킹 + document_chunks 저장 (OFFICIAL_GUIDE)
  Stage 3B: 문제 구조 추출 + 저장 (DUMP)
  Stage 4A: 배치 임베딩 생성 + chunk_embeddings 저장 (OFFICIAL_GUIDE)
  Stage 4B: 키워드 토픽 매핑 (OFFICIAL_GUIDE)
  Stage 5: IVFFlat REINDEX + pipeline_runs → COMPLETED / FAILED

FastAPI BackgroundTasks에서 run_pipeline()을 호출한다:
    background_tasks.add_task(run_pipeline, run_id, db)

docs/05-rag-pipeline.md 섹션 4-2 기준 구현.
NOTE: quality_score는 Stage 3A(save_chunks) 시점에 즉시 계산·저장한다.
      docs Stage 3A 다이어그램의 quality_score=null → Stage 5 업데이트 흐름과
      달리 단일 INSERT로 처리 (구현 단순화).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import _get_factory
from app.models.document_version import DocumentVersion
from app.models.learning_document import LearningDocument
from app.models.pipeline_run import PipelineRun
from app.pipeline.chunker import hierarchical_chunk
from app.pipeline.embedder import embed_chunks
from app.pipeline.indexer import (
    map_chunk_topics,
    reindex_vector,
    save_chunks,
    save_dump_questions,
    save_embeddings,
)
from app.pipeline.parser import extract_text_blocks, parse_dump_pages

logger = logging.getLogger(__name__)


async def run_pipeline(
    pipeline_run_id: uuid.UUID,
    _unused_db: AsyncSession | None = None,
) -> None:
    """파이프라인 전체 실행 진입점.

    pipeline_runs.status 전이:
        PENDING → PROCESSING → COMPLETED | FAILED

    BackgroundTask로 호출될 때 request-scoped session이 닫히는 문제를 방지하기 위해
    내부에서 독립적인 세션을 직접 생성한다.
    docs/05-rag-pipeline.md 섹션 2-2 상태 전이도 참고.
    """
    async with _get_factory()() as db:
        await _run_pipeline_with_session(pipeline_run_id, db)


async def _run_pipeline_with_session(
    pipeline_run_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    run: PipelineRun | None = await db.get(PipelineRun, pipeline_run_id)
    if run is None:
        logger.error("run_pipeline: pipeline_run_id=%s 레코드 없음", pipeline_run_id)
        return

    doc: LearningDocument | None = await db.get(LearningDocument, run.learning_document_id)
    if doc is None:
        await _fail(db, run, "learning_document 레코드를 찾을 수 없습니다.")
        return

    dv: DocumentVersion | None = (
        await db.get(DocumentVersion, run.document_version_id)
        if run.document_version_id
        else None
    )

    # Stage 1: PENDING → PROCESSING
    await _set_status(db, run, "PROCESSING", started_at=datetime.now(timezone.utc))

    try:
        # Stage 2: PDF 파싱
        pages = extract_text_blocks(doc.file_path)

        if doc.source_type == "OFFICIAL_GUIDE":
            if dv is None:
                raise ValueError("OFFICIAL_GUIDE 파이프라인에 document_version이 필요합니다.")
            await _process_official_guide(db, run, dv, doc, pages)
        elif doc.source_type == "DUMP":
            await _process_dump(db, run, doc, pages)
        else:
            raise ValueError(f"알 수 없는 source_type: {doc.source_type!r}")

        # Stage 5: COMPLETED
        await _set_status(db, run, "COMPLETED", completed_at=datetime.now(timezone.utc))

    except Exception as exc:
        logger.exception(
            "run_pipeline 실패: pipeline_run_id=%s source_type=%s",
            pipeline_run_id,
            getattr(doc, "source_type", "unknown"),
        )
        await _fail(db, run, str(exc))


# ──────────────────────────────────────────────
# OFFICIAL_GUIDE 경로
# ──────────────────────────────────────────────

async def _process_official_guide(
    db: AsyncSession,
    run: PipelineRun,
    dv: DocumentVersion,
    doc: LearningDocument,
    pages: list[dict],
) -> None:
    """Stage 3A~4B: 계층적 청킹 → 임베딩 → 토픽 매핑."""

    # Stage 3A: 계층적 청킹
    chunks = hierarchical_chunk(pages, document_version_id=str(dv.id))
    if not chunks:
        raise ValueError("청킹 결과 0개: PDF 텍스트 추출 후 청크가 생성되지 않았습니다.")

    await _update_total(db, run, len(chunks))

    # Stage 3A: document_chunks DB 저장
    chunk_results = await save_chunks(db, chunks)

    # Stage 4A: 배치 임베딩 생성 + chunk_embeddings 저장
    embeddings = await embed_chunks(chunk_results)
    embedded_count = await save_embeddings(db, chunk_results, embeddings)
    await _add_processed(db, run, embedded_count)

    # Stage 4B: 토픽 매핑 (키워드 매칭, docs/05-rag-pipeline.md 섹션 6-2)
    for cr in chunk_results:
        await map_chunk_topics(db, cr["chunk_id"], cr["chunk_text"], doc.certification_id)

    # Stage 5: IVFFlat REINDEX (chunk_embeddings 대량 삽입 후 recall 유지)
    await reindex_vector(db)


# ──────────────────────────────────────────────
# DUMP 경로
# ──────────────────────────────────────────────

async def _process_dump(
    db: AsyncSession,
    run: PipelineRun,
    doc: LearningDocument,
    pages: list[dict],
) -> None:
    """Stage 3B: 덤프 문제 구조 추출 → questions/choices/answer_explanations 저장.

    DUMP 경로는 chunk_embeddings를 생성하지 않으므로 IVFFlat REINDEX 생략.
    """
    questions = parse_dump_pages(pages)
    if not questions:
        raise ValueError("덤프 문제 0개 추출: 패턴 A/B 모두 매칭 실패.")

    await _update_total(db, run, len(questions))

    saved = await save_dump_questions(
        db,
        certification_id=doc.certification_id,
        questions=questions,
    )
    await _add_processed(db, run, saved)


# ──────────────────────────────────────────────
# 상태 업데이트 헬퍼
# ──────────────────────────────────────────────

async def _set_status(
    db: AsyncSession,
    run: PipelineRun,
    status: str,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    values: dict = {"status": status, "updated_at": datetime.now(timezone.utc)}
    if started_at:
        values["started_at"] = started_at
    if completed_at:
        values["completed_at"] = completed_at
    await db.execute(update(PipelineRun).where(PipelineRun.id == run.id).values(**values))
    await db.commit()


async def _fail(db: AsyncSession, run: PipelineRun, error_message: str) -> None:
    now = datetime.now(timezone.utc)
    await db.execute(
        update(PipelineRun)
        .where(PipelineRun.id == run.id)
        .values(
            status="FAILED",
            error_message=error_message,
            completed_at=now,
            updated_at=now,
        )
    )
    await db.commit()
    logger.error("pipeline FAILED: run_id=%s — %s", run.id, error_message)


async def _update_total(db: AsyncSession, run: PipelineRun, total: int) -> None:
    await db.execute(
        update(PipelineRun)
        .where(PipelineRun.id == run.id)
        .values(total_chunks=total, updated_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def _add_processed(db: AsyncSession, run: PipelineRun, count: int) -> None:
    await db.execute(
        text(
            "UPDATE pipeline_runs "
            "SET processed_chunks = processed_chunks + :n, updated_at = now() "
            "WHERE id = :run_id"
        ),
        {"n": count, "run_id": str(run.id)},
    )
    await db.commit()
