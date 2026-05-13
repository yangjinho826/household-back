import uuid

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class FixedExpense(BaseEntity):
    """고정지출 참조 — fixed_expenses 테이블

    금액은 보유하지 않음. 실제 지출 내역은 transactions 에 fixed_expense_id 로 매핑되어
    기록되고, 월별 사용액은 거래 합산으로 구함.
    """

    __tablename__ = "fixed_expenses"

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    day_of_month: Mapped[int] = mapped_column(Integer, nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False)
