import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class DocumentVersion(Base, CommonMixin):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "learning_document_id",
            "version_number",
            name="uq_document_versions_doc_ver",
        ),
    )

    learning_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
