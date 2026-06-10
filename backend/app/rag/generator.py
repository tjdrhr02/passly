"""RAG 답변 생성 모듈 — Gemini API.

docs/05-rag-pipeline.md 섹션 8-3 참고.
시스템 프롬프트: 출처 청크 기반으로만 답변.
"""
from __future__ import annotations
import logging
from app.core.ai_client import generate_content

logger = logging.getLogger(__name__)


async def generate_answer(
    question: str,
    chunks: list[dict],
    certification_name: str = "",
) -> str:
    """검색된 청크를 컨텍스트로 Gemini 답변 생성."""
    if not chunks:
        return "관련 학습 자료를 찾지 못했습니다. PDF를 먼저 업로드하고 파이프라인을 완료해주세요."

    context_parts = []
    for i, chunk in enumerate(chunks[:10], 1):
        text = chunk.get("chunk_summary") or chunk.get("chunk_text", "")
        context_parts.append(f"[{i}] {text[:500]}")
    context = "\n\n".join(context_parts)

    prompt = f"""You are a {certification_name or 'IT certification'} exam tutor.
Answer ONLY based on provided study materials. If not in materials, say so clearly.
Cite sources as [1], [2], etc.

Materials:
{context}

Question: {question}

Answer:"""

    try:
        return await generate_content(prompt)
    except Exception as exc:
        logger.error("generate_answer 실패: %s", exc)
        return "답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
