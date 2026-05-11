from uuid import UUID

from sqlalchemy import and_, func, select
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

    async def search_by_household_id(
        self,
        household_id: UUID,
        *,
        search_term: str | None = None,
        account_type: str | None = None,
        is_archived: bool | None = None,
    ) -> list[Account]:
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

        result = await self.db.execute(
            select(Account)
            .where(and_(*conditions))
            .order_by(Account.sort_order.asc(), Account.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

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
