import uuid
from datetime import date, datetime

from sqlalchemy import CHAR, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class Household(BaseEntity):
    """가계부 그룹 — households 테이블"""

    __tablename__ = "households"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    started_at: Mapped[date] = mapped_column(nullable=False)


class HouseholdMember(BaseEntity):
    """가계부 멤버십 — household_members 테이블"""

    __tablename__ = "household_members"

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(nullable=False)
