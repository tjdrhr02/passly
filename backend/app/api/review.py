"""복습 API 라우터.

GET /api/exam-sessions                        — 세션 목록
GET /api/exam-sessions/{session_id}/attempts  — 전체 풀이 이력
GET /api/exam-sessions/{session_id}/wrong-attempts — 오답만

NOTE: user_attempts DELETE 엔드포인트 미제공.
      user_attempts.is_deleted 변경 금지.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.models.answer_explanation import AnswerExplanation
from app.models.certification import Certification
from app.models.choice import Choice
from app.models.exam_session import ExamSession
from app.models.question import Question
from app.models.user import User
from app.models.user_attempt import UserAttempt
from app.schemas.common import SuccessResponse
from app.schemas.review import (
    AttemptDetail,
    ChoiceInAttempt,
    SessionAttemptsResponse,
    SessionListItem,
    SessionListResponse,
)

router = APIRouter(prefix="/api/exam-sessions", tags=["review"])


async def _get_session_or_404(
    session_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> ExamSession:
    """세션 조회 + 소유자 검증."""
    result = await db.execute(
        select(ExamSession).where(
            ExamSession.id == session_id,
            ExamSession.is_deleted == False,  # noqa: E712
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다.")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="접근 권한이 없습니다.")
    return session


async def _build_attempt_details(
    attempts: list[UserAttempt],
    db: AsyncSession,
) -> list[AttemptDetail]:
    """UserAttempt 목록 → AttemptDetail 목록 변환."""
    details: list[AttemptDetail] = []
    for attempt in attempts:
        # 문제 조회
        q_result = await db.execute(
            select(Question).where(Question.id == attempt.question_id)
        )
        question = q_result.scalar_one_or_none()
        if question is None:
            continue

        # 선택지 조회
        c_result = await db.execute(
            select(Choice)
            .where(Choice.question_id == question.id)
            .order_by(Choice.order_num)
        )
        choices = c_result.scalars().all()

        # 해설 조회
        e_result = await db.execute(
            select(AnswerExplanation).where(AnswerExplanation.question_id == question.id)
        )
        explanation = e_result.scalar_one_or_none()

        # selected_choice_ids: JSONB → list[uuid.UUID]
        raw_ids: list = attempt.selected_choice_ids or []
        selected_ids = [uuid.UUID(str(cid)) for cid in raw_ids]

        details.append(
            AttemptDetail(
                attempt_id=attempt.id,
                question_id=question.id,
                question_text=question.question_text,
                question_type=question.question_type,
                selected_choice_ids=selected_ids,
                is_correct=attempt.is_correct,
                choices=[
                    ChoiceInAttempt(
                        id=c.id,
                        choice_label=c.choice_label,
                        choice_text=c.choice_text,
                        is_correct=c.is_correct,
                    )
                    for c in choices
                ],
                explanation_text=explanation.explanation_text if explanation else None,
            )
        )
    return details


@router.get("", response_model=SuccessResponse[SessionListResponse])
async def list_exam_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[SessionListResponse]:
    """현재 사용자의 시험 세션 목록 (최신순)."""
    result = await db.execute(
        select(ExamSession)
        .where(
            ExamSession.user_id == current_user.id,
            ExamSession.is_deleted == False,  # noqa: E712
        )
        .order_by(ExamSession.created_at.desc())
    )
    sessions = result.scalars().all()

    items: list[SessionListItem] = []
    for s in sessions:
        # 자격증 이름 조회
        cert_result = await db.execute(
            select(Certification).where(Certification.id == s.certification_id)
        )
        cert = cert_result.scalar_one_or_none()
        cert_name = cert.name if cert else ""

        score = (s.correct_count / s.total_questions * 100.0) if s.total_questions > 0 else 0.0

        items.append(
            SessionListItem(
                session_id=s.id,
                certification_name=cert_name,
                exam_mode=s.exam_mode,
                total_questions=s.total_questions,
                correct_count=s.correct_count,
                score_percent=round(score, 2),
                started_at=s.started_at,
                completed_at=s.completed_at,
            )
        )

    return SuccessResponse(data=SessionListResponse(sessions=items, total=len(items)))


@router.get(
    "/{session_id}/attempts",
    response_model=SuccessResponse[SessionAttemptsResponse],
)
async def get_session_attempts(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[SessionAttemptsResponse]:
    """세션의 전체 풀이 이력."""
    session = await _get_session_or_404(session_id, current_user, db)

    result = await db.execute(
        select(UserAttempt).where(
            UserAttempt.session_id == session_id,
            UserAttempt.is_deleted == False,  # noqa: E712
        )
    )
    attempts = result.scalars().all()

    cert_result = await db.execute(
        select(Certification).where(Certification.id == session.certification_id)
    )
    cert = cert_result.scalar_one_or_none()
    cert_name = cert.name if cert else ""

    details = await _build_attempt_details(list(attempts), db)

    return SuccessResponse(
        data=SessionAttemptsResponse(
            session_id=session.id,
            certification_name=cert_name,
            exam_mode=session.exam_mode,
            attempts=details,
            total_questions=session.total_questions,
            correct_count=session.correct_count,
        )
    )


@router.get(
    "/{session_id}/wrong-attempts",
    response_model=SuccessResponse[SessionAttemptsResponse],
)
async def get_session_wrong_attempts(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[SessionAttemptsResponse]:
    """세션의 오답 풀이 이력."""
    session = await _get_session_or_404(session_id, current_user, db)

    result = await db.execute(
        select(UserAttempt).where(
            UserAttempt.session_id == session_id,
            UserAttempt.is_deleted == False,  # noqa: E712
            UserAttempt.is_correct == False,  # noqa: E712
        )
    )
    attempts = result.scalars().all()

    cert_result = await db.execute(
        select(Certification).where(Certification.id == session.certification_id)
    )
    cert = cert_result.scalar_one_or_none()
    cert_name = cert.name if cert else ""

    details = await _build_attempt_details(list(attempts), db)

    return SuccessResponse(
        data=SessionAttemptsResponse(
            session_id=session.id,
            certification_name=cert_name,
            exam_mode=session.exam_mode,
            attempts=details,
            total_questions=session.total_questions,
            correct_count=session.correct_count,
        )
    )
