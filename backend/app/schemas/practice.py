"""연습 모드 스키마.

POST /api/practice/generate — 문제 생성
POST /api/practice/submit   — 답안 제출 및 채점
"""
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class PracticeGenerateRequest(BaseModel):
    certification_id: uuid.UUID
    domain_id: Optional[uuid.UUID] = None
    topic_id: Optional[uuid.UUID] = None
    difficulty: Optional[str] = None
    count: int = Field(default=10, ge=1, le=20)


class ChoiceWithCorrect(BaseModel):
    id: uuid.UUID
    choice_label: str
    choice_text: str
    is_correct: bool
    order_num: int


class GeneratedQuestion(BaseModel):
    id: uuid.UUID
    question_text: str
    question_type: str
    difficulty: str
    choices: list[ChoiceWithCorrect]
    explanation_text: Optional[str] = None


class PracticeGenerateResponse(BaseModel):
    questions: list[GeneratedQuestion]
    generated_count: int


class PracticeSubmitRequest(BaseModel):
    question_id: uuid.UUID
    selected_choice_ids: list[uuid.UUID]
    session_id: Optional[uuid.UUID] = None


class PracticeSubmitResponse(BaseModel):
    is_correct: bool
    correct_choice_ids: list[uuid.UUID]
    explanation_text: Optional[str] = None
