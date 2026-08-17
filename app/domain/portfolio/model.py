import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class PortfolioItem(BaseEntity):
    """보유 종목 — portfolio_items 테이블"""

    __tablename__ = "portfolio_items"
    __table_args__ = (
        Index("idx_portfolio_household", "household_id"),
        Index("idx_portfolio_account", "account_id"),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    # KRW 가 진실 원천 — 계좌잔액·순자산·스냅샷 합산이 전부 이 컬럼을 통화 구분 없이 더한다.
    avg_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # 거래통화 병행 보관 — 화면 표시와 종목 자체 수익률(환율 변동 제외)용.
    # market 에서 도출한다(Market.currency).
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'KRW'"),
    )
    # NULL = 달러 원본을 모르는 상태. 마이그레이션 이전 거래로만 구성된 종목이 그렇다.
    avg_price_ccy: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    current_price_ccy: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 4), nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PortfolioTransaction(BaseEntity):
    """자산 거래 이력 — portfolio_transactions 테이블"""

    __tablename__ = "portfolio_transactions"
    __table_args__ = (
        Index("idx_pt_household_date", "household_id", text("tx_date DESC")),
        Index("idx_pt_account", "account_id"),
        Index("idx_pt_item", "portfolio_item_id"),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    portfolio_item_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    pt_type: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # 매매 수수료 — 매수는 원가(평단)에 가산, 매도는 실현손익에서 차감.
    # 기존 거래는 0 이라 도입 전 계산과 동일하다.
    fee: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default=text("0"),
    )
    # 거래통화 원본 + 거래시점 환율. price/fee(KRW)는 이 값에 fx_rate 를 곱해 만든다.
    # 마이그레이션 이전 거래는 원본 달러가가 저장된 적이 없어 *_ccy 가 NULL 이다
    # (price 는 이미 원화 환산값이라 되돌릴 수 없다).
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'KRW'"),
    )
    price_ccy: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    fee_ccy: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    fx_rate: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, server_default=text("1"),
    )
    tx_date: Mapped[date] = mapped_column(Date, nullable=False)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 매도 실현손익 — SELL 만 채워짐. 매도시점 이동평균 평단 기준 건별 박제.
    # BUY 또는 R2 이전 SELL 은 NULL (매도시점 평단 복원 불가).
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    realized_cost_basis: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True,
    )
    # 거래통화 기준 실현손익 — 환율 변동이 섞이지 않은 종목 자체 성과.
    # 기여 거래 중 price_ccy 가 없는 게 하나라도 있으면 NULL.
    realized_pnl_ccy: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True,
    )
    realized_cost_basis_ccy: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True,
    )


class PortfolioValueHistory(BaseEntity):
    """종목별 월별 평가액 박제 — portfolio_value_history 테이블"""

    __tablename__ = "portfolio_value_history"
    __table_args__ = (
        Index("idx_pvh_household", "household_id"),
        Index("idx_pvh_account", "account_id"),
        Index("idx_pvh_item_date", "portfolio_item_id", text("snapshot_date DESC")),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    portfolio_item_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    valuation: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
