import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class ManualAsset(BaseEntity):
    """수동자산(부동산·연금) — manual_assets 테이블.

    market/quantity/avg_price 가 안 맞는 비투자 자산. 전용계좌(account_id)로
    roll-up 되어 총자산·배분에 자동 반영된다. 현재 평가액만 보관 —
    과거 평가이력(carry-forward)은 월별 배분추이가 필요한 R5a-3 에서 추가.
    """

    __tablename__ = "manual_assets"
    __table_args__ = (
        Index("idx_manual_asset_household", "household_id"),
        Index("idx_manual_asset_account", "account_id"),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 자산 성격 — REAL_ESTATE / PENSION (AssetClass 와 동일 문자열)
    asset_class: Mapped[str] = mapped_column(String(20), nullable=False)
    current_valuation: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    valued_at: Mapped[date] = mapped_column(Date, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False)
