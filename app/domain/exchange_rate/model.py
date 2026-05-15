from datetime import date
from decimal import Decimal

from sqlalchemy import CHAR, Date, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model import BaseEntity


class ExchangeRate(BaseEntity):
    """환율 시계열 — exchange_rates 테이블.

    (snapshot_date, base_currency, quote_currency) 가 논리 unique.
    매일 1회 박제. 동일 날짜 재실행 시 갱신.
    """

    __tablename__ = "exchange_rates"
    __table_args__ = (
        Index(
            "uq_exchange_rates_date_pair",
            "snapshot_date",
            "base_currency",
            "quote_currency",
            unique=True,
        ),
    )

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    base_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
