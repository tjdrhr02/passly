from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    certification_id: UUID


class SourceChunk(BaseModel):
    chunk_id: str
    chunk_text: str
    rrf_score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
