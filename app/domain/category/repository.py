from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.category.model import Category


class CategoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(self, category_id: UUID) -> Category | None:
        result = await self.db.execute(
            select(Category).where(
                and_(
                    Category.id == category_id,
                    Category.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_household_id(self, household_id: UUID) -> list[Category]:
        result = await self.db.execute(
            select(Category)
            .where(
                and_(
                    Category.household_id == household_id,
                    Category.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(Category.kind.asc(), Category.sort_order.asc(), Category.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

    async def find_by_ids(self, ids: list[UUID]) -> list[Category]:
        if not ids:
            return []
        result = await self.db.execute(
            select(Category).where(Category.id.in_(ids))
        )
        return list(result.scalars().all())

    async def max_sort_order(self, household_id: UUID, kind: str) -> int:
        result = await self.db.execute(
            select(func.max(Category.sort_order)).where(
                and_(
                    Category.household_id == household_id,
                    Category.kind == kind,
                    Category.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar() or 0

    async def save(self, category: Category) -> None:
        self.db.add(category)
        await self.db.flush()
