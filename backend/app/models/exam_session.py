import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class ExamSession(Base, CommonMixin):
    __tablename__ = "exam_sessions"
    __table_args__ = (
        CheckConstraint("total_questions >= 0", name="chk_exam_sessions_total_questions"),
        CheckConstraint("correct_count >= 0", name="chk_exam_sessions_correct_count"),
        CheckConstraint("correct_count <= total_questions", name="chk_exam_sessions_correct_lte_total"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    certification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("certifications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    exam_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # [반정규화] 대시보드 집계 성능 최적화 — docs/03-erd-physical.md 섹션 8
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
