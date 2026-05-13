import uuid
from datetime import date, datetime

from sqlalchemy import CHAR, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class Household(BaseEntity):
    """가계부 그룹 — households 테이블"""

    __tablename__ = "households"
    __table_args__ = (
        Index("idx_households_owner", "owner_id"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    started_at: Mapped[date] = mapped_column(nullable=False)


class HouseholdMember(BaseEntity):
    """가계부 멤버십 — household_members 테이블"""

    __tablename__ = "household_members"
    __table_args__ = (
        Index("idx_members_user", "user_id"),
        Index("idx_members_household", "household_id"),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
