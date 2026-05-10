import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class Transaction(BaseEntity):
    """거래 — transactions 테이블"""

    __tablename__ = "transactions"

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    tx_type: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    tx_date: Mapped[date] = mapped_column(Date, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    to_account_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    paid_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    is_fixed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
