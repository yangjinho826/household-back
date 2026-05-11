import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class PortfolioItem(BaseEntity):
    """보유 종목 — portfolio_items 테이블"""

    __tablename__ = "portfolio_items"

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    ticker: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PortfolioTransaction(BaseEntity):
    """자산 거래 이력 — portfolio_transactions 테이블"""

    __tablename__ = "portfolio_transactions"

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    portfolio_item_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    ticker: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pt_type: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    tx_date: Mapped[date] = mapped_column(Date, nullable=False)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)


class PortfolioValueHistory(BaseEntity):
    """종목별 월별 평가액 박제 — portfolio_value_history 테이블"""

    __tablename__ = "portfolio_value_history"

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    portfolio_item_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    valuation: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
