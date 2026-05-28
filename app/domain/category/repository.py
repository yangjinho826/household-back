from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
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

    async def search_by_household_id(
        self,
        household_id: UUID,
        *,
        search_term: str | None = None,
        kind: str | None = None,
        is_archived: bool | None = None,
    ) -> list[Category]:
        """검색/필터 — search_term 은 name LIKE %term%"""
        conditions = [
            Category.household_id == household_id,
            Category.data_stat_cd == DataStatus.ACTIVE,
        ]
        if search_term:
            conditions.append(Category.name.ilike(f"%{search_term.strip()}%"))
        if kind:
            conditions.append(Category.kind == kind)
        if is_archived is not None:
            conditions.append(Category.is_archived == is_archived)

        result = await self.db.execute(
            select(Category)
            .where(and_(*conditions))
            .order_by(Category.kind.asc(), Category.sort_order.asc(), Category.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

    def _build_search_conditions(
        self,
        household_id: UUID,
        *,
        search_term: str | None,
        kind: str | None,
        is_archived: bool | None,
    ):
        conditions = [
            Category.household_id == household_id,
            Category.data_stat_cd == DataStatus.ACTIVE,
        ]
        if search_term:
            conditions.append(Category.name.ilike(f"%{search_term.strip()}%"))
        if kind:
            conditions.append(Category.kind == kind)
        if is_archived is not None:
            conditions.append(Category.is_archived == is_archived)
        return conditions

    @staticmethod
    def _cursor_after(cursor: str | None):
        """frst_reg_dt DESC, id DESC 기준 cursor — `{datetime_iso}|{uuid}` 평문."""
        if not cursor:
            return None
        try:
            dt_str, id_str = cursor.split("|", 1)
            cur_dt = datetime.fromisoformat(dt_str)
            cur_id = UUID(id_str)
        except (ValueError, AttributeError):
            return None
        return or_(
            Category.frst_reg_dt < cur_dt,
            and_(Category.frst_reg_dt == cur_dt, Category.id < cur_id),
        )

    async def list_by_cursor(
        self,
        household_id: UUID,
        *,
        search_term: str | None = None,
        kind: str | None = None,
        is_archived: bool | None = None,
        cursor: str | None = None,
        limit: int = 30,
    ) -> list[Category]:
        """무한 스크롤 — limit+1 로 has_next 판정."""
        conds = self._build_search_conditions(
            household_id,
            search_term=search_term,
            kind=kind,
            is_archived=is_archived,
        )
        cursor_cond = self._cursor_after(cursor)
        if cursor_cond is not None:
            conds.append(cursor_cond)
        result = await self.db.execute(
            select(Category)
            .where(and_(*conds))
            .order_by(Category.frst_reg_dt.desc(), Category.id.desc())
            .limit(limit + 1)
        )
        return list(result.scalars().all())

    async def count_search(
        self,
        household_id: UUID,
        *,
        search_term: str | None = None,
        kind: str | None = None,
        is_archived: bool | None = None,
    ) -> int:
        conds = self._build_search_conditions(
            household_id,
            search_term=search_term,
            kind=kind,
            is_archived=is_archived,
        )
        result = await self.db.execute(
            select(func.count(Category.id)).where(and_(*conds))
        )
        return result.scalar() or 0

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
