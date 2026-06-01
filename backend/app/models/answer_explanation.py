from __future__ import annotations
from typing import Optional
import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class AnswerExplanation(Base, CommonMixin):
    __tablename__ = "answer_explanations"

    # UNIQUE: 문제당 해설 1개 보장 (DB 레벨)
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    explanation_text: Mapped[str] = mapped_column(Text, nullable=False)
    # NULLABLE: 해설 근거 청크 없을 수 있음
    source_chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="RESTRICT"),
        nullable=True,
    )
