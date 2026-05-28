from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.account.model import Account


class AccountRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(self, account_id: UUID) -> Account | None:
        result = await self.db.execute(
            select(Account).where(
                and_(
                    Account.id == account_id,
                    Account.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_household_id(self, household_id: UUID) -> list[Account]:
        """내부용 전체 조회 — overview 합산/snapshot 등에서 사용. cursor 페이징과 별개."""
        result = await self.db.execute(
            select(Account)
            .where(
                and_(
                    Account.household_id == household_id,
                    Account.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(Account.sort_order.asc(), Account.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

    def _build_search_conditions(
        self,
        household_id: UUID,
        *,
        search_term: str | None,
        account_type: str | None,
        is_archived: bool | None,
    ):
        conditions = [
            Account.household_id == household_id,
            Account.data_stat_cd == DataStatus.ACTIVE,
        ]
        if search_term:
            conditions.append(Account.name.ilike(f"%{search_term.strip()}%"))
        if account_type:
            conditions.append(Account.account_type == account_type)
        if is_archived is not None:
            conditions.append(Account.is_archived == is_archived)
        return conditions

    async def search_by_household_id(
        self,
        household_id: UUID,
        *,
        search_term: str | None = None,
        account_type: str | None = None,
        is_archived: bool | None = None,
    ) -> list[Account]:
        """내부용 (overview/snapshot/portfolio 등) — sort_order 정렬 유지.
        외부 list endpoint 는 `list_by_cursor` 사용."""
        result = await self.db.execute(
            select(Account)
            .where(and_(*self._build_search_conditions(
                household_id,
                search_term=search_term,
                account_type=account_type,
                is_archived=is_archived,
            )))
            .order_by(Account.sort_order.asc(), Account.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

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
            Account.frst_reg_dt < cur_dt,
            and_(Account.frst_reg_dt == cur_dt, Account.id < cur_id),
        )

    async def list_by_cursor(
        self,
        household_id: UUID,
        *,
        search_term: str | None = None,
        account_type: str | None = None,
        is_archived: bool | None = None,
        cursor: str | None = None,
        limit: int = 30,
    ) -> list[Account]:
        """무한 스크롤 — limit+1 로 has_next 판정."""
        conds = self._build_search_conditions(
            household_id,
            search_term=search_term,
            account_type=account_type,
            is_archived=is_archived,
        )
        cursor_cond = self._cursor_after(cursor)
        if cursor_cond is not None:
            conds.append(cursor_cond)
        result = await self.db.execute(
            select(Account)
            .where(and_(*conds))
            .order_by(Account.frst_reg_dt.desc(), Account.id.desc())
            .limit(limit + 1)
        )
        return list(result.scalars().all())

    async def count_search(
        self,
        household_id: UUID,
        *,
        search_term: str | None = None,
        account_type: str | None = None,
        is_archived: bool | None = None,
    ) -> int:
        """관리 페이지의 '전체 N개' 표시용. 무한 스크롤 자체는 hasNext 만 신뢰."""
        conds = self._build_search_conditions(
            household_id,
            search_term=search_term,
            account_type=account_type,
            is_archived=is_archived,
        )
        result = await self.db.execute(
            select(func.count(Account.id)).where(and_(*conds))
        )
        return result.scalar() or 0

    async def find_by_ids(self, ids: list[UUID]) -> list[Account]:
        if not ids:
            return []
        result = await self.db.execute(
            select(Account).where(Account.id.in_(ids))
        )
        return list(result.scalars().all())

    async def max_sort_order(self, household_id: UUID) -> int:
        result = await self.db.execute(
            select(func.max(Account.sort_order)).where(
                and_(
                    Account.household_id == household_id,
                    Account.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar() or 0

    async def save(self, account: Account) -> None:
        self.db.add(account)
        await self.db.flush()
