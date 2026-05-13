import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class Category(BaseEntity):
    """카테고리 — categories 테이블"""

    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("kind IN ('EXPENSE', 'INCOME')", name="ck_categories_kind"),
        Index("idx_categories_household", "household_id", "kind"),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False)
