"""Gemini API / Vertex AI 통합 임베딩 클라이언트.

USE_VERTEX_AI=false → Gemini Developer API (로컬)
USE_VERTEX_AI=true  → Vertex AI (GCP Cloud Run)
코드 변경 없이 환경변수 하나로 전환 (AGENTS.md 섹션 2, docs/05-rag-pipeline.md 섹션 9).
"""
from __future__ import annotations

import os
from typing import Optional

import google.generativeai as genai

USE_VERTEX_AI: bool = os.getenv("USE_VERTEX_AI", "false").lower() == "true"
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
GCP_REGION: str = os.getenv("GCP_REGION", "asia-northeast3")

EMBED_MODEL_NAME = "text-embedding-004"
LLM_MODEL_NAME = "gemini-1.5-flash"

_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    if USE_VERTEX_AI:
        import vertexai
        vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    else:
        genai.configure(api_key=GEMINI_API_KEY)
    _configured = True


async def embed_texts(
    texts: list[str],
    task_type: str = "retrieval_document",
) -> list[Optional[list[float]]]:
    """임베딩 생성. 실패 항목은 None 반환.

    Args:
        texts: 임베딩할 텍스트 목록
        task_type: "retrieval_document" (문서) | "retrieval_query" (검색 쿼리)
    """
    _ensure_configured()

    if USE_VERTEX_AI:
        from vertexai.language_models import TextEmbeddingModel
        model = TextEmbeddingModel.from_pretrained(EMBED_MODEL_NAME)
        embeddings = model.get_embeddings(texts, task_type=task_type)
        return [e.values for e in embeddings]

    response = genai.embed_content(
        model=f"models/{EMBED_MODEL_NAME}",
        content=texts,
        task_type=task_type,
    )
    raw = response.get("embedding") or response.get("embeddings", [])
    # 단일 텍스트 → list[float], 복수 → list[list[float]]
    if texts and isinstance(raw[0], float):
        return [raw]
    return raw
