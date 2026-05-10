from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.fixed.model import FixedExpense


class FixedRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(self, fixed_id: UUID) -> FixedExpense | None:
        result = await self.db.execute(
            select(FixedExpense).where(
                and_(
                    FixedExpense.id == fixed_id,
                    FixedExpense.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_household_id(self, household_id: UUID) -> list[FixedExpense]:
        result = await self.db.execute(
            select(FixedExpense)
            .where(
                and_(
                    FixedExpense.household_id == household_id,
                    FixedExpense.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(FixedExpense.sort_order.asc(), FixedExpense.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

    async def max_sort_order(self, household_id: UUID) -> int:
        result = await self.db.execute(
            select(func.max(FixedExpense.sort_order)).where(
                and_(
                    FixedExpense.household_id == household_id,
                    FixedExpense.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar() or 0

    async def save(self, fixed: FixedExpense) -> None:
        self.db.add(fixed)
        await self.db.flush()
