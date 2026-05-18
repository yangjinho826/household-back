from decimal import Decimal

from sqlalchemy import CHAR, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class CurrencyRate(BaseEntity):
    """환율 — (base, quote) 쌍당 1 row, 매번 update.

    last_mdfcn_dt (BaseEntity onupdate) 가 마지막 갱신 시각.
    """

    __tablename__ = "currency_rates"
    __table_args__ = (
        UniqueConstraint(
            "base_currency", "quote_currency",
            name="uq_currency_rates_pair",
        ),
    )

    base_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
