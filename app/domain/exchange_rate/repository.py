from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.exchange_rate.enum import CurrencyCode
from app.domain.exchange_rate.model import CurrencyRate


class CurrencyRateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_pair(
        self, base: CurrencyCode, quote: CurrencyCode,
    ) -> CurrencyRate | None:
        result = await self.db.execute(
            select(CurrencyRate).where(
                and_(
                    CurrencyRate.base_currency == base,
                    CurrencyRate.quote_currency == quote,
                    CurrencyRate.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def save(self, rate: CurrencyRate) -> None:
        self.db.add(rate)
        await self.db.flush()
