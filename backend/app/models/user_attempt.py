from __future__ import annotations
from typing import Optional
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class UserAttempt(Base, CommonMixin):
    """[불변 이력] 시험 응답 기록.

    is_deleted = true 변경 금지. DELETE 엔드포인트 미제공.
    근거: docs/02-erd-logical.md 결정 4 / docs/00-data-standard.md 섹션 4
    """

    __tablename__ = "user_attempts"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # 복수 선택 답안 UUID 배열 (JSONB)
    selected_choice_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="'[]'"
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    time_spent_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
