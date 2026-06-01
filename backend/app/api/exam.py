"""시험 API 라우터.

GET  /api/certifications                      — 자격증 목록
GET  /api/certifications/{id}/domains         — 영역 목록
POST /api/exam-sessions                       — 세션 생성
GET  /api/exam-sessions/{id}/questions        — 문제 조회
POST /api/exam-sessions/{id}/submit           — 답안 제출
GET  /api/exam-sessions/{id}/result           — 결과 조회
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.models.answer_explanation import AnswerExplanation
from app.models.certification import Certification
from app.models.choice import Choice
from app.models.exam_domain import ExamDomain
from app.models.exam_session import ExamSession
from app.models.question import Question
from app.models.topic import Topic
from app.models.user import User
from app.models.user_attempt import UserAttempt
from app.schemas.common import SuccessResponse
from app.schemas.exam import (
    CertificationResponse,
    ChoiceResponse,
    DomainScore,
    ExamDomainResponse,
    ExamResultResponse,
    ExamSessionCreateRequest,
    ExamSessionQuestionsResponse,
    ExamSubmitRequest,
    QuestionResponse,
    WrongAttemptDetail,
)

router = APIRouter(prefix="/api", tags=["exam"])


# ---------------------------------------------------------------------------
# GET /api/certifications
# ---------------------------------------------------------------------------

@router.get(
    "/certifications",
    response_model=SuccessResponse[list[CertificationResponse]],
)
async def list_certifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SuccessResponse[list[CertificationResponse]]:
    result = await db.execute(
        select(Certification).where(
            Certification.is_deleted == False,  # noqa: E712
            Certification.is_active == True,  # noqa: E712
        )
    )
    certs = result.scalars().all()
    return SuccessResponse(data=[CertificationResponse.model_validate(c) for c in certs])


# ---------------------------------------------------------------------------
# GET /api/certifications/{certification_id}/domains
# ---------------------------------------------------------------------------

@router.get(
    "/certifications/{certification_id}/domains",
    response_model=SuccessResponse[list[ExamDomainResponse]],
)
async def list_domains(
    certification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SuccessResponse[list[ExamDomainResponse]]:
    result = await db.execute(
        select(ExamDomain)
        .where(
            ExamDomain.certification_id == certification_id,
            ExamDomain.is_deleted == False,  # noqa: E712
        )
        .order_by(ExamDomain.order_num)
    )
    domains = result.scalars().all()
    return SuccessResponse(data=[ExamDomainResponse.model_validate(d) for d in domains])


# ---------------------------------------------------------------------------
# POST /api/exam-sessions
# ---------------------------------------------------------------------------

@router.post(
    "/exam-sessions",
    response_model=SuccessResponse[dict],
    status_code=status.HTTP_201_CREATED,
)
async def create_exam_session(
    body: ExamSessionCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SuccessResponse[dict]:
    session = ExamSession(
        user_id=current_user.id,
        certification_id=body.certification_id,
        exam_mode=body.exam_mode,
        total_questions=body.question_count,
        time_limit_seconds=body.time_limit_seconds,
    )
    db.add(session)
    await db.flush()
    session_id = session.id
    await db.commit()

    return SuccessResponse(
        data={
            "session_id": str(session_id),
            "exam_mode": body.exam_mode,
            "total_questions": body.question_count,
            "time_limit_seconds": body.time_limit_seconds,
        }
    )


# ---------------------------------------------------------------------------
# GET /api/exam-sessions/{session_id}/questions
# ---------------------------------------------------------------------------

@router.get(
    "/exam-sessions/{session_id}/questions",
    response_model=SuccessResponse[ExamSessionQuestionsResponse],
)
async def get_session_questions(
    session_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SuccessResponse[ExamSessionQuestionsResponse]:
    # 세션 조회 및 소유자 검증
    session_result = await db.execute(
        select(ExamSession).where(
            ExamSession.id == session_id,
            ExamSession.is_deleted == False,  # noqa: E712
        )
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="시험 세션을 찾을 수 없습니다.")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="접근 권한이 없습니다.")

    # questions JOIN topics JOIN exam_domains — domain_name 포함
    q_result = await db.execute(
        select(Question, ExamDomain.name.label("domain_name"))
        .join(Topic, Question.topic_id == Topic.id)
        .join(ExamDomain, Topic.exam_domain_id == ExamDomain.id)
        .where(
            Question.certification_id == session.certification_id,
            Question.source_type.in_(["DUMP", "GENERATED"]),
            Question.is_active == True,  # noqa: E712
            Question.is_deleted == False,  # noqa: E712
        )
        .order_by(func.random())
        .limit(session.total_questions)
    )
    rows = q_result.all()

    # choices 조회 (is_correct 미포함 — 시험 중 정답 노출 금지)
    question_ids = [row.Question.id for row in rows]
    choices_result = await db.execute(
        select(Choice).where(
            Choice.question_id.in_(question_ids),
            Choice.is_deleted == False,  # noqa: E712
        )
    )
    all_choices = choices_result.scalars().all()

    # question_id → choices 매핑
    choices_map: dict[uuid.UUID, list[Choice]] = {}
    for c in all_choices:
        choices_map.setdefault(c.question_id, []).append(c)

    questions: list[QuestionResponse] = []
    for row in rows:
        q = row.Question
        domain_name = row.domain_name
        q_choices = choices_map.get(q.id, [])
        random.shuffle(q_choices)
        choice_responses = [
            ChoiceResponse(
                id=c.id,
                choice_label=c.choice_label,
                choice_text=c.choice_text,
                order_num=c.order_num,
            )
            for c in q_choices
        ]
        questions.append(
            QuestionResponse(
                id=q.id,
                question_text=q.question_text,
                question_type=q.question_type,
                difficulty=q.difficulty,
                choices=choice_responses,
                domain_name=domain_name,
            )
        )

    return SuccessResponse(
        data=ExamSessionQuestionsResponse(
            session_id=session_id,
            questions=questions,
            total_questions=len(questions),
            time_limit_seconds=session.time_limit_seconds,
        )
    )


# ---------------------------------------------------------------------------
# POST /api/exam-sessions/{session_id}/submit
# ---------------------------------------------------------------------------

@router.post(
    "/exam-sessions/{session_id}/submit",
    response_model=SuccessResponse[dict],
)
async def submit_exam(
    session_id: uuid.UUID,
    body: ExamSubmitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SuccessResponse[dict]:
    # 세션 소유자 검증
    session_result = await db.execute(
        select(ExamSession).where(
            ExamSession.id == session_id,
            ExamSession.is_deleted == False,  # noqa: E712
        )
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="시험 세션을 찾을 수 없습니다.")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="접근 권한이 없습니다.")
    if session.is_completed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 제출된 시험 세션입니다.")

    # 해당 질문들의 choices 조회 (is_correct 포함 — 채점용)
    question_ids = [a.question_id for a in body.answers]
    choices_result = await db.execute(
        select(Choice).where(
            Choice.question_id.in_(question_ids),
            Choice.is_deleted == False,  # noqa: E712
        )
    )
    all_choices = choices_result.scalars().all()

    # question_id → correct choice ids 매핑
    correct_map: dict[uuid.UUID, set[uuid.UUID]] = {}
    for c in all_choices:
        if c.is_correct:
            correct_map.setdefault(c.question_id, set()).add(c.id)

    correct_count = 0

    # 단일 트랜잭션: user_attempts 삽입 + exam_sessions 업데이트
    for answer in body.answers:
        correct_ids = correct_map.get(answer.question_id, set())
        selected_ids = set(answer.selected_choice_ids)
        is_correct = selected_ids == correct_ids
        if is_correct:
            correct_count += 1

        attempt = UserAttempt(
            session_id=session_id,
            question_id=answer.question_id,
            selected_choice_ids=[str(cid) for cid in answer.selected_choice_ids],
            is_correct=is_correct,
        )
        db.add(attempt)

    # exam_sessions 업데이트
    session.correct_count = correct_count
    session.is_completed = True
    session.completed_at = datetime.now(timezone.utc)
    if body.elapsed_seconds is not None:
        session.elapsed_seconds = body.elapsed_seconds

    await db.commit()

    return SuccessResponse(
        data={
            "correct_count": correct_count,
            "total": len(body.answers),
        }
    )


# ---------------------------------------------------------------------------
# GET /api/exam-sessions/{session_id}/result
# ---------------------------------------------------------------------------

@router.get(
    "/exam-sessions/{session_id}/result",
    response_model=SuccessResponse[ExamResultResponse],
)
async def get_exam_result(
    session_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SuccessResponse[ExamResultResponse]:
    # 세션 소유자 검증 + is_completed 확인
    session_result = await db.execute(
        select(ExamSession).where(
            ExamSession.id == session_id,
            ExamSession.is_deleted == False,  # noqa: E712
        )
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="시험 세션을 찾을 수 없습니다.")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="접근 권한이 없습니다.")
    if not session.is_completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="아직 제출되지 않은 세션입니다.")

    # user_attempts 조회
    attempts_result = await db.execute(
        select(UserAttempt).where(
            UserAttempt.session_id == session_id,
            UserAttempt.is_deleted == False,  # noqa: E712
        )
    )
    attempts = attempts_result.scalars().all()

    if not attempts:
        return SuccessResponse(
            data=ExamResultResponse(
                session_id=session_id,
                total_questions=session.total_questions,
                correct_count=session.correct_count,
                score_percent=0.0,
                domain_scores=[],
                wrong_attempts=[],
            )
        )

    question_ids = [a.question_id for a in attempts]

    # questions + topics + exam_domains JOIN
    q_result = await db.execute(
        select(Question, ExamDomain.name.label("domain_name"))
        .join(Topic, Question.topic_id == Topic.id)
        .join(ExamDomain, Topic.exam_domain_id == ExamDomain.id)
        .where(Question.id.in_(question_ids))
    )
    q_rows = q_result.all()
    question_map: dict[uuid.UUID, tuple[Question, str]] = {
        row.Question.id: (row.Question, row.domain_name) for row in q_rows
    }

    # choices 조회 (정답 식별용 — is_correct 포함)
    choices_result = await db.execute(
        select(Choice).where(
            Choice.question_id.in_(question_ids),
            Choice.is_deleted == False,  # noqa: E712
        )
    )
    all_choices = choices_result.scalars().all()
    correct_map: dict[uuid.UUID, list[uuid.UUID]] = {}
    for c in all_choices:
        if c.is_correct:
            correct_map.setdefault(c.question_id, []).append(c.id)

    # answer_explanations 조회 (optional)
    exp_result = await db.execute(
        select(AnswerExplanation).where(
            AnswerExplanation.question_id.in_(question_ids),
            AnswerExplanation.is_deleted == False,  # noqa: E712
        )
    )
    explanations = {e.question_id: e.explanation_text for e in exp_result.scalars().all()}

    # 영역별 집계
    domain_total: dict[str, int] = {}
    domain_correct: dict[str, int] = {}
    wrong_attempts: list[WrongAttemptDetail] = []

    for attempt in attempts:
        q_entry = question_map.get(attempt.question_id)
        domain_name = q_entry[1] if q_entry else "Unknown"
        domain_total[domain_name] = domain_total.get(domain_name, 0) + 1
        if attempt.is_correct:
            domain_correct[domain_name] = domain_correct.get(domain_name, 0) + 1
        else:
            q_obj = q_entry[0] if q_entry else None
            selected_ids = [uuid.UUID(cid) for cid in (attempt.selected_choice_ids or [])]
            correct_ids = correct_map.get(attempt.question_id, [])
            wrong_attempts.append(
                WrongAttemptDetail(
                    question_id=attempt.question_id,
                    question_text=q_obj.question_text if q_obj else "",
                    selected_choice_ids=selected_ids,
                    correct_choice_ids=correct_ids,
                    explanation_text=explanations.get(attempt.question_id),
                )
            )

    domain_scores = [
        DomainScore(
            domain_name=dn,
            total_questions=domain_total[dn],
            correct_count=domain_correct.get(dn, 0),
            score_percent=round(domain_correct.get(dn, 0) / domain_total[dn] * 100, 1),
        )
        for dn in domain_total
    ]

    total = session.total_questions
    correct = session.correct_count
    score_pct = round(correct / total * 100, 1) if total > 0 else 0.0

    return SuccessResponse(
        data=ExamResultResponse(
            session_id=session_id,
            total_questions=total,
            correct_count=correct,
            score_percent=score_pct,
            domain_scores=domain_scores,
            wrong_attempts=wrong_attempts,
        )
    )
