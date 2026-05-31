import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class ChunkEmbedding(Base, CommonMixin):
    """pgvector 임베딩 저장 테이블. document_chunks와 1:1 분리 (비벡터 쿼리 성능 보호).

    설계 근거: docs/04-vector-schema.md 섹션 2-3
    """

    __tablename__ = "chunk_embeddings"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    # vector(768): Gemini text-embedding-004 출력 차원
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)
    # 모델 교체 이력 추적용 — docs/04-vector-schema.md 섹션 3-1
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
