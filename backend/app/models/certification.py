from __future__ import annotations
from typing import Optional
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CommonMixin


class Certification(Base, CommonMixin):
    __tablename__ = "certifications"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str] = mapped_column(String(100), nullable=False)
    exam_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
