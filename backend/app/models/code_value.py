from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class CodeValue(Base, CommonMixin):
    __tablename__ = "code_values"
    __table_args__ = (
        UniqueConstraint("code_group", "code_value", name="uq_code_values_group_value"),
    )

    code_group: Mapped[str] = mapped_column(String(50), nullable=False)
    code_value: Mapped[str] = mapped_column(String(50), nullable=False)
    code_name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
