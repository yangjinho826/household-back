import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Index, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class AccountSnapshot(BaseEntity):
    """월말 통장 잔액 스냅샷 — account_snapshots 테이블"""

    __tablename__ = "account_snapshots"
    __table_args__ = (
        Index("idx_snapshots_account_date", "account_id", text("snapshot_date DESC")),
        Index("idx_snapshots_date", text("snapshot_date DESC")),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
