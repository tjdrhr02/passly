from __future__ import annotations
from typing import Optional
import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class Question(Base, CommonMixin):
    __tablename__ = "questions"

    certification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("certifications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # NULLABLE: 덤프 파싱 문제는 출처 청크 없음 (docs/02-erd-logical.md 결정 5)
    source_chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="RESTRICT"),
        nullable=True,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    difficulty: Mapped[str] = mapped_column(
        String(50), nullable=False, default="INTERMEDIATE", server_default="INTERMEDIATE"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
