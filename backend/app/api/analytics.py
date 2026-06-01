"""Analytics API 라우터.

GET /api/analytics/summary        — 자격증별 전체 정답률 요약
GET /api/analytics/recent-sessions — 최근 완료 시험 세션 목록
GET /api/analytics/weak-domains   — 영역별 오답률 Top 3
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.models.exam_session import ExamSession
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsSummaryResponse,
    CertificationSummary,
    RecentSessionItem,
    RecentSessionsResponse,
    WeakDomainItem,
    WeakDomainsResponse,
)
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary", response_model=SuccessResponse[AnalyticsSummaryResponse])
async def get_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[AnalyticsSummaryResponse]:
    """현재 사용자의 자격증별 전체 정답률 요약."""
    sql = text("""
        SELECT c.id::text, c.name,
               COUNT(ua.id) as total_attempts,
               SUM(CASE WHEN ua.is_correct = true THEN 1 ELSE 0 END) as correct_count
        FROM user_attempts ua
        JOIN questions q ON ua.question_id = q.id
        JOIN certifications c ON q.certification_id = c.id
        JOIN exam_sessions es ON ua.session_id = es.id
        WHERE es.user_id = :user_id
          AND ua.is_deleted = false
          AND es.is_deleted = false
        GROUP BY c.id, c.name
    """)
    result = await db.execute(sql, {"user_id": str(current_user.id)})
    rows = result.fetchall()

    certifications: list[CertificationSummary] = []
    total_attempts = 0
    for row in rows:
        cert_id, cert_name, attempts, correct = row
        attempts = int(attempts)
        correct = int(correct)
        accuracy = correct / attempts * 100 if attempts > 0 else 0.0
        certifications.append(
            CertificationSummary(
                certification_id=cert_id,
                certification_name=cert_name,
                total_attempts=attempts,
                correct_count=correct,
                accuracy_percent=round(accuracy, 2),
            )
        )
        total_attempts += attempts

    sessions_result = await db.execute(
        select(ExamSession).where(
            ExamSession.user_id == current_user.id,
            ExamSession.is_completed == True,  # noqa: E712
            ExamSession.is_deleted == False,  # noqa: E712
        )
    )
    total_sessions = len(sessions_result.scalars().all())

    return SuccessResponse(
        data=AnalyticsSummaryResponse(
            certifications=certifications,
            total_sessions=total_sessions,
            total_questions_answered=total_attempts,
        )
    )


@router.get("/recent-sessions", response_model=SuccessResponse[RecentSessionsResponse])
async def get_recent_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=5, le=20),
) -> SuccessResponse[RecentSessionsResponse]:
    """최근 완료 시험 세션 목록."""
    sql = text("""
        SELECT es.id::text,
               c.name as certification_name,
               es.exam_mode,
               es.total_questions,
               es.correct_count,
               es.completed_at
        FROM exam_sessions es
        JOIN certifications c ON es.certification_id = c.id
        WHERE es.user_id = :user_id
          AND es.is_completed = true
          AND es.is_deleted = false
        ORDER BY es.completed_at DESC
        LIMIT :limit
    """)
    result = await db.execute(sql, {"user_id": str(current_user.id), "limit": limit})
    rows = result.fetchall()

    sessions: list[RecentSessionItem] = []
    for row in rows:
        session_id, cert_name, exam_mode, total_q, correct, completed_at = row
        total_q = int(total_q)
        correct = int(correct)
        score_percent = correct / total_q * 100 if total_q > 0 else 0.0
        sessions.append(
            RecentSessionItem(
                session_id=session_id,
                certification_name=cert_name,
                exam_mode=exam_mode,
                total_questions=total_q,
                correct_count=correct,
                score_percent=round(score_percent, 2),
                completed_at=completed_at,
            )
        )

    return SuccessResponse(data=RecentSessionsResponse(sessions=sessions))


@router.get("/weak-domains", response_model=SuccessResponse[WeakDomainsResponse])
async def get_weak_domains(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[WeakDomainsResponse]:
    """영역별 오답률 Top 3."""
    sql = text("""
        SELECT ed.name as domain_name,
               c.name as certification_name,
               COUNT(ua.id) as total_attempts,
               SUM(CASE WHEN ua.is_correct = false THEN 1 ELSE 0 END) as wrong_count
        FROM user_attempts ua
        JOIN questions q ON ua.question_id = q.id
        JOIN topics t ON q.topic_id = t.id
        JOIN exam_domains ed ON t.exam_domain_id = ed.id
        JOIN certifications c ON q.certification_id = c.id
        JOIN exam_sessions es ON ua.session_id = es.id
        WHERE es.user_id = :user_id
          AND ua.is_deleted = false
          AND es.is_deleted = false
        GROUP BY ed.id, ed.name, c.id, c.name
        HAVING COUNT(ua.id) > 0
        ORDER BY (SUM(CASE WHEN ua.is_correct = false THEN 1 ELSE 0 END)::float / COUNT(ua.id)) DESC
        LIMIT 3
    """)
    result = await db.execute(sql, {"user_id": str(current_user.id)})
    rows = result.fetchall()

    domains: list[WeakDomainItem] = []
    for row in rows:
        domain_name, cert_name, total_attempts, wrong_count = row
        total_attempts = int(total_attempts)
        wrong_count = int(wrong_count)
        error_rate = wrong_count / total_attempts * 100 if total_attempts > 0 else 0.0
        domains.append(
            WeakDomainItem(
                domain_name=domain_name,
                certification_name=cert_name,
                total_attempts=total_attempts,
                wrong_count=wrong_count,
                error_rate_percent=round(error_rate, 2),
            )
        )

    return SuccessResponse(data=WeakDomainsResponse(domains=domains))
