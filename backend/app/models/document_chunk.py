from __future__ import annotations
from typing import Optional
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Computed, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class DocumentChunk(Base, CommonMixin):
    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint(
            "quality_score IS NULL OR quality_score BETWEEN 0 AND 100",
            name="chk_document_chunks_quality_score",
        ),
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunk_order: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    difficulty: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    access_level: Mapped[str] = mapped_column(
        String(50), nullable=False, default="SHARED", server_default="SHARED"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # Generated column — DB가 chunk_text 기반으로 자동 계산 (FTS용)
    chunk_tsv: Mapped[Optional[str]] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(chunk_text, ''))", persisted=True),

        nullable=True,
    )
