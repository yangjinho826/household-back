import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class AccountSnapshot(BaseEntity):
    """월말 통장 잔액 스냅샷 — account_snapshots 테이블"""

    __tablename__ = "account_snapshots"

    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
