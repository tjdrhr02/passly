"""Analytics 스키마.

대시보드 API 응답 모델 정의.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CertificationSummary(BaseModel):
    certification_id: str
    certification_name: str
    total_attempts: int
    correct_count: int
    accuracy_percent: float


class AnalyticsSummaryResponse(BaseModel):
    certifications: list[CertificationSummary]
    total_sessions: int
    total_questions_answered: int


class RecentSessionItem(BaseModel):
    session_id: str
    certification_name: str
    exam_mode: str
    total_questions: int
    correct_count: int
    score_percent: float
    completed_at: datetime


class RecentSessionsResponse(BaseModel):
    sessions: list[RecentSessionItem]


class WeakDomainItem(BaseModel):
    domain_name: str
    certification_name: str
    total_attempts: int
    wrong_count: int
    error_rate_percent: float


class WeakDomainsResponse(BaseModel):
    domains: list[WeakDomainItem]
