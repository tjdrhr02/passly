"""배치 임베딩 생성 모듈.

- USE_VERTEX_AI 환경변수로 Gemini API / Vertex AI 분기 (ai_client.py 위임)
- 배치 크기 100건 (docs/05-rag-pipeline.md 섹션 6-1)
- 실패 시 지수 백오프 3회 재시도
- 최종 실패 청크는 None 반환 (건너뜀 후 error_message에 카운트)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.core.ai_client import embed_texts

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # 초 (지수 백오프 기준)


async def embed_chunks(
    chunks: list[dict],
) -> list[Optional[list[float]]]:
    """청크 리스트를 BATCH_SIZE 단위 배치로 임베딩을 생성한다.

    Args:
        chunks: [{"chunk_text": str, ...}, ...] 형식의 청크 목록

    Returns:
        chunks와 동일한 길이. 실패한 청크 위치는 None.
    """
    all_embeddings: list[Optional[list[float]]] = []

    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_start: batch_start + BATCH_SIZE]
        texts = [c["chunk_text"] for c in batch]
        batch_result = await _embed_with_retry(texts, batch_start)
        all_embeddings.extend(batch_result)

    return all_embeddings


async def _embed_with_retry(
    texts: list[str],
    batch_start: int,
) -> list[Optional[list[float]]]:
    """배치 단위 임베딩 + 지수 백오프 재시도 (최대 MAX_RETRIES회)."""
    for attempt in range(MAX_RETRIES):
        try:
            result = await embed_texts(texts, task_type="retrieval_document")
            return [r if isinstance(r, list) else None for r in result]
        except Exception as exc:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "임베딩 배치 실패 (batch_start=%d, attempt=%d/%d): %s — %.1f초 후 재시도",
                batch_start, attempt + 1, MAX_RETRIES, exc, delay,
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "임베딩 배치 최종 실패 (batch_start=%d): None %d개 반환",
                    batch_start, len(texts),
                )
                return [None] * len(texts)

    return [None] * len(texts)  # 방어 코드
