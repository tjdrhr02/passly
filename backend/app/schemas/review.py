from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SessionListItem(BaseModel):
    session_id: uuid.UUID
    certification_name: str
    exam_mode: str
    total_questions: int
    correct_count: int
    score_percent: float
    started_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]
    total: int


class ChoiceInAttempt(BaseModel):
    id: uuid.UUID
    choice_label: str
    choice_text: str
    is_correct: bool

    model_config = {"from_attributes": True}


class AttemptDetail(BaseModel):
    attempt_id: uuid.UUID
    question_id: uuid.UUID
    question_text: str
    question_type: str
    selected_choice_ids: list[uuid.UUID]
    is_correct: bool
    choices: list[ChoiceInAttempt]
    explanation_text: Optional[str] = None


class SessionAttemptsResponse(BaseModel):
    session_id: uuid.UUID
    certification_name: str
    exam_mode: str
    attempts: list[AttemptDetail]
    total_questions: int
    correct_count: int
