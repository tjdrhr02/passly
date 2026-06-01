from __future__ import annotations
from typing import Optional
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class PipelineRun(Base, CommonMixin):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint("processed_chunks >= 0", name="chk_pipeline_runs_processed_chunks"),
    )

    learning_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # NULLABLE: 파이프라인 완료 전에는 버전 없음
    document_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING", server_default="PENDING"
    )
    total_chunks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processed_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
