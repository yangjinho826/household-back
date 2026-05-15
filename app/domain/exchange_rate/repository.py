from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.exchange_rate.model import ExchangeRate


class ExchangeRateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_date(
        self, snapshot_date: date, base: str, quote: str,
    ) -> ExchangeRate | None:
        """특정 날짜의 환율 row. 같은 날 잡 재실행 시 update 분기용."""
        result = await self.db.execute(
            select(ExchangeRate).where(
                and_(
                    ExchangeRate.snapshot_date == snapshot_date,
                    ExchangeRate.base_currency == base,
                    ExchangeRate.quote_currency == quote,
                    ExchangeRate.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_latest(self, base: str, quote: str) -> ExchangeRate | None:
        """가장 최근 active 환율 — USD 종목 갱신 시 fall-back 용."""
        result = await self.db.execute(
            select(ExchangeRate)
            .where(
                and_(
                    ExchangeRate.base_currency == base,
                    ExchangeRate.quote_currency == quote,
                    ExchangeRate.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(ExchangeRate.snapshot_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save(self, rate: ExchangeRate) -> None:
        self.db.add(rate)
        await self.db.flush()
