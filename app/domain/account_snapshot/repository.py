from datetime import date
from uuid import UUID

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.account.model import Account
from app.domain.account_snapshot.model import AccountSnapshot


class AccountSnapshotRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def has_active_for_month(self, household_id: UUID, month_first_day: date) -> bool:
        """해당 가계부의 그 달 1일자 active 스냅샷이 1개라도 있는지"""
        stmt = select(
            exists()
            .where(
                and_(
                    AccountSnapshot.snapshot_date == month_first_day,
                    AccountSnapshot.data_stat_cd == DataStatus.ACTIVE,
                    AccountSnapshot.account_id == Account.id,
                    Account.household_id == household_id,
                )
            )
        )
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def find_by_household_and_range(
        self, household_id: UUID, from_date: date, to_date: date,
    ) -> list[AccountSnapshot]:
        """가계부 + 기간 범위 스냅샷 조회 (account JOIN 으로 household 필터)"""
        stmt = (
            select(AccountSnapshot)
            .join(Account, Account.id == AccountSnapshot.account_id)
            .where(
                and_(
                    Account.household_id == household_id,
                    AccountSnapshot.data_stat_cd == DataStatus.ACTIVE,
                    AccountSnapshot.snapshot_date >= from_date,
                    AccountSnapshot.snapshot_date <= to_date,
                )
            )
            .order_by(AccountSnapshot.snapshot_date.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def save_all(self, snapshots: list[AccountSnapshot]) -> None:
        if not snapshots:
            return
        self.db.add_all(snapshots)
        await self.db.flush()
