"""Gemini API / Vertex AI 통합 임베딩 + LLM 클라이언트.

USE_VERTEX_AI=false → Gemini Developer API (로컬)
USE_VERTEX_AI=true  → Vertex AI REST API via ADC (google-cloud-aiplatform 의존 없음)
                      httpx + google-auth(transitive dep) 조합으로 처리
코드 변경 없이 환경변수 하나로 전환 (AGENTS.md 섹션 2, docs/05-rag-pipeline.md 섹션 9).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import google.generativeai as genai
import httpx

logger = logging.getLogger(__name__)

USE_VERTEX_AI: bool = os.getenv("USE_VERTEX_AI", "false").lower() == "true"
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
GCP_REGION: str = os.getenv("GCP_REGION", "asia-northeast3")

EMBED_MODEL_NAME = "text-embedding-004"
LLM_MODEL_NAME = "gemini-2.5-flash"

_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    if not USE_VERTEX_AI:
        genai.configure(api_key=GEMINI_API_KEY)
    _configured = True


def _get_vertex_token() -> str:
    """ADC(Application Default Credentials)로 Vertex AI Bearer 토큰 획득 (동기)."""
    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token  # type: ignore[return-value]


def _get_gemini_token() -> str:
    """ADC로 generativelanguage.googleapis.com용 Bearer 토큰 획득 (동기).

    generativelanguage.googleapis.com은 generative-language 스코프가 필요하다.
    Cloud Run 서비스 계정에서 정상 작동한다.
    """
    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/generative-language"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token  # type: ignore[return-value]


def get_llm_model() -> genai.GenerativeModel:
    """Gemini Developer API용 LLM 모델 반환 (로컬 전용).

    Vertex AI 경로에서는 이 함수 대신 generate_content()를 직접 사용한다.
    """
    _ensure_configured()
    return genai.GenerativeModel(LLM_MODEL_NAME)


async def generate_content(prompt: str) -> str:
    """Gemini LLM 텍스트 생성.

    USE_VERTEX_AI=true  → Vertex AI REST API (비동기)
    USE_VERTEX_AI=false → google-generativeai SDK (로컬 개발용)
    """
    _ensure_configured()

    if USE_VERTEX_AI:
        try:
            return await _generate_via_vertex_rest(prompt)
        except Exception as vertex_exc:
            logger.warning("Vertex AI generateContent 실패, Gemini API 키 폴백: %s", vertex_exc)
            return await _generate_via_gemini_api_key(prompt)

    model = genai.GenerativeModel(LLM_MODEL_NAME)
    response = await model.generate_content_async(prompt)
    return response.text


async def _generate_via_gemini_api_key(prompt: str) -> str:
    """generativelanguage.googleapis.com generateContent REST API — API 키 인증.

    Cloud Run 서비스 계정 토큰은 cloud-platform 스코프만 지원하므로
    generativelanguage.googleapis.com에는 API 키 방식을 사용한다.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL_NAME}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            url,
            params={"key": GEMINI_API_KEY},
            json=body,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

    return data["candidates"][0]["content"]["parts"][0]["text"]


async def _generate_via_vertex_rest(prompt: str) -> str:
    """Vertex AI generateContent REST API 비동기 호출 (레거시, 현재 미사용)."""
    token = await asyncio.to_thread(_get_vertex_token)

    url = (
        f"https://{GCP_REGION}-aiplatform.googleapis.com/v1/projects/"
        f"{GCP_PROJECT_ID}/locations/{GCP_REGION}/publishers/google/models/"
        f"{LLM_MODEL_NAME}:generateContent"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()

    return data["candidates"][0]["content"]["parts"][0]["text"]


async def embed_texts(
    texts: list[str],
    task_type: str = "retrieval_document",
) -> list[Optional[list[float]]]:
    """임베딩 생성. 실패 항목은 None 반환.

    USE_VERTEX_AI=true  → Vertex AI REST API (비동기, google-auth + httpx)
    USE_VERTEX_AI=false → google-generativeai embed_content
    """
    _ensure_configured()

    if USE_VERTEX_AI:
        return await _embed_via_vertex_rest(texts, task_type)

    response = genai.embed_content(
        model=f"models/{EMBED_MODEL_NAME}",
        content=texts,
        task_type=task_type,
    )
    raw = response.get("embedding") or []
    if texts and raw and isinstance(raw[0], float):
        return [raw]
    return raw  # type: ignore[return-value]


async def _embed_via_vertex_rest(
    texts: list[str],
    task_type: str,
) -> list[Optional[list[float]]]:
    """Vertex AI Embedding REST API 비동기 호출.

    동기 토큰 갱신은 asyncio.to_thread로 이벤트 루프 블로킹 방지.
    """
    task_type_map = {
        "retrieval_document": "RETRIEVAL_DOCUMENT",
        "retrieval_query": "RETRIEVAL_QUERY",
        "semantic_similarity": "SEMANTIC_SIMILARITY",
        "classification": "CLASSIFICATION",
        "clustering": "CLUSTERING",
    }
    vertex_task = task_type_map.get(task_type, "RETRIEVAL_DOCUMENT")

    token = await asyncio.to_thread(_get_vertex_token)

    url = (
        f"https://{GCP_REGION}-aiplatform.googleapis.com/v1/projects/"
        f"{GCP_PROJECT_ID}/locations/{GCP_REGION}/publishers/google/models/"
        f"{EMBED_MODEL_NAME}:predict"
    )
    instances = [{"content": t, "task_type": vertex_task} for t in texts]

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            url,
            json={"instances": instances},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()

    return [pred["embeddings"]["values"] for pred in data.get("predictions", [])]
