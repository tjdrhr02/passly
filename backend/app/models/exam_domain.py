import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class ExamDomain(Base, CommonMixin):
    __tablename__ = "exam_domains"
    __table_args__ = (
        CheckConstraint("weight_percent BETWEEN 1 AND 100", name="chk_exam_domains_weight_percent"),
    )

    certification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("certifications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    weight_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    order_num: Mapped[int] = mapped_column(Integer, nullable=False)
