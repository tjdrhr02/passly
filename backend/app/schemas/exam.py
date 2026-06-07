from __future__ import annotations
from pydantic import BaseModel, Field

from typing import Optional
from uuid import UUID


from app.schemas.common import SuccessResponse  # noqa: F401 — re-export convenience


class CertificationResponse(BaseModel):
    id: UUID
    name: str
    vendor: str
    exam_code: str

    model_config = {"from_attributes": True}


class ExamDomainResponse(BaseModel):
    id: UUID
    name: str
    weight_percent: int
    order_num: int

    model_config = {"from_attributes": True}


class ExamSessionCreateRequest(BaseModel):
    certification_id: UUID
    exam_mode: str  # TIMED | PRACTICE
    question_count: int
    time_limit_seconds: Optional[int] = None


class ExamSessionResponse(BaseModel):
    id: UUID
    exam_mode: str
    total_questions: int
    time_limit_seconds: Optional[int]

    model_config = {"from_attributes": True}


class ChoiceResponse(BaseModel):
    """is_correct 미포함 — 시험 중 정답 노출 금지."""

    id: UUID
    choice_label: str
    choice_text: str
    order_num: int

    model_config = {"from_attributes": True}


class QuestionResponse(BaseModel):
    id: UUID
    question_text: str
    question_type: str
    difficulty: str
    choices: list[ChoiceResponse]
    domain_name: str

    model_config = {"from_attributes": True}


class ExamSessionQuestionsResponse(BaseModel):
    session_id: UUID
    questions: list[QuestionResponse]
    total_questions: int
    time_limit_seconds: Optional[int]


class AttemptAnswer(BaseModel):
    question_id: UUID
    selected_choice_ids: list[UUID]


class ExamSubmitRequest(BaseModel):
    session_id: UUID
    answers: list[AttemptAnswer]
    elapsed_seconds: Optional[int] = None


class WrongAttemptDetail(BaseModel):
    question_id: UUID
    question_text: str
    selected_choice_ids: list[UUID]
    correct_choice_ids: list[UUID]
    explanation_text: Optional[str] = None


class DomainScore(BaseModel):
    domain_name: str
    total_questions: int
    correct_count: int
    score_percent: float


class ExamResultResponse(BaseModel):
    session_id: UUID
    total_questions: int
    correct_count: int
    score_percent: float
    domain_scores: list[DomainScore]
    wrong_attempts: list[WrongAttemptDetail]


class ExamDomainCreateRequest(BaseModel):
    name: str
    weight_percent: int = Field(ge=1, le=100)


class CertificationCreateRequest(BaseModel):
    name: str
    vendor: str
    exam_code: str
    domains: list[ExamDomainCreateRequest] = []
