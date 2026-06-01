"""연습 모드 API 라우터.

POST /api/practice/generate — DB에서 문제 조회
POST /api/practice/submit   — 답안 채점 (즉시 반환, DB 저장 없음)
"""
from __future__ import annotations

import uuid
from typing import Annotated

import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.models.answer_explanation import AnswerExplanation
from app.models.choice import Choice
from app.models.exam_domain import ExamDomain
from app.models.question import Question
from app.models.topic import Topic
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.practice import (
    ChoiceWithCorrect,
    GeneratedQuestion,
    PracticeGenerateRequest,
    PracticeGenerateResponse,
    PracticeSubmitRequest,
    PracticeSubmitResponse,
)

router = APIRouter(prefix="/api", tags=["practice"])


@router.post(
    "/practice/generate",
    response_model=SuccessResponse[PracticeGenerateResponse],
)
async def generate_practice(
    body: PracticeGenerateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> SuccessResponse[PracticeGenerateResponse]:
    """자격증/도메인/토픽/난이도 필터로 랜덤 문제를 반환한다."""

    # 1. 문제 조회 (RANDOM LIMIT count)
    stmt = (
        select(Question)
        .join(Topic, Question.topic_id == Topic.id)
        .join(ExamDomain, Topic.exam_domain_id == ExamDomain.id)
        .where(
            Question.certification_id == body.certification_id,
            Question.is_active == True,  # noqa: E712
            Question.is_deleted == False,  # noqa: E712
        )
    )

    if body.domain_id is not None:
        stmt = stmt.where(ExamDomain.id == body.domain_id)

    if body.topic_id is not None:
        stmt = stmt.where(Question.topic_id == body.topic_id)

    if body.difficulty is not None:
        stmt = stmt.where(Question.difficulty == body.difficulty)

    stmt = stmt.order_by(sqlalchemy.func.random()).limit(body.count)

    result = await db.execute(stmt)
    questions: list[Question] = list(result.scalars().all())

    if not questions:
        return SuccessResponse(
            data=PracticeGenerateResponse(questions=[], generated_count=0),
            message="해당 조건에 맞는 문제가 없습니다. 다른 조건을 선택해 주세요.",
        )

    question_ids = [q.id for q in questions]

    # 2. choices 일괄 조회
    choices_result = await db.execute(
        select(Choice)
        .where(Choice.question_id.in_(question_ids))
        .order_by(Choice.question_id, Choice.order_num)
    )
    all_choices: list[Choice] = list(choices_result.scalars().all())

    choices_by_question: dict[uuid.UUID, list[Choice]] = {}
    for c in all_choices:
        choices_by_question.setdefault(c.question_id, []).append(c)

    # 3. 해설 일괄 조회
    explanations_result = await db.execute(
        select(AnswerExplanation).where(
            AnswerExplanation.question_id.in_(question_ids)
        )
    )
    explanations_by_question: dict[uuid.UUID, str] = {
        e.question_id: e.explanation_text
        for e in explanations_result.scalars().all()
    }

    # 4. 응답 조립
    generated: list[GeneratedQuestion] = []
    for q in questions:
        choices_for_q = choices_by_question.get(q.id, [])
        generated.append(
            GeneratedQuestion(
                id=q.id,
                question_text=q.question_text,
                question_type=q.question_type,
                difficulty=q.difficulty,
                choices=[
                    ChoiceWithCorrect(
                        id=c.id,
                        choice_label=c.choice_label,
                        choice_text=c.choice_text,
                        is_correct=c.is_correct,
                        order_num=c.order_num,
                    )
                    for c in choices_for_q
                ],
                explanation_text=explanations_by_question.get(q.id),
            )
        )

    return SuccessResponse(
        data=PracticeGenerateResponse(
            questions=generated,
            generated_count=len(generated),
        )
    )


@router.post(
    "/practice/submit",
    response_model=SuccessResponse[PracticeSubmitResponse],
)
async def submit_practice(
    body: PracticeSubmitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> SuccessResponse[PracticeSubmitResponse]:
    """답안 채점 후 결과를 즉시 반환한다. DB에는 저장하지 않는다."""

    # 정답 선택지 조회
    correct_result = await db.execute(
        select(Choice).where(
            Choice.question_id == body.question_id,
            Choice.is_correct == True,  # noqa: E712
        )
    )
    correct_choices: list[Choice] = list(correct_result.scalars().all())

    if not correct_choices:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 문제를 찾을 수 없습니다.",
        )

    correct_ids = {c.id for c in correct_choices}
    selected_ids = set(body.selected_choice_ids)
    is_correct = selected_ids == correct_ids

    # 해설 조회 (없으면 None)
    explanation_result = await db.execute(
        select(AnswerExplanation).where(
            AnswerExplanation.question_id == body.question_id
        )
    )
    explanation = explanation_result.scalar_one_or_none()
    explanation_text = explanation.explanation_text if explanation else None

    return SuccessResponse(
        data=PracticeSubmitResponse(
            is_correct=is_correct,
            correct_choice_ids=list(correct_ids),
            explanation_text=explanation_text,
        )
    )
