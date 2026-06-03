from datetime import date
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, select, update
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

    async def oldest_active_month(self, household_id: UUID) -> date | None:
        """그 가계부의 가장 오래된 박제월 — catch-up 하한(데이터 시작 전은 안 채움)."""
        stmt = (
            select(func.min(AccountSnapshot.snapshot_date))
            .join(Account, Account.id == AccountSnapshot.account_id)
            .where(
                and_(
                    Account.household_id == household_id,
                    AccountSnapshot.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar()

    async def find_by_account_and_range(
        self, account_id: UUID, from_date: date, to_date: date,
    ) -> list[AccountSnapshot]:
        """계좌 단위 + 기간 범위 스냅샷 조회 (계좌별 리포트용)"""
        stmt = (
            select(AccountSnapshot)
            .where(
                and_(
                    AccountSnapshot.account_id == account_id,
                    AccountSnapshot.data_stat_cd == DataStatus.ACTIVE,
                    AccountSnapshot.snapshot_date >= from_date,
                    AccountSnapshot.snapshot_date <= to_date,
                )
            )
            .order_by(AccountSnapshot.snapshot_date.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_for_household_month(
        self, household_id: UUID, month_first: date,
    ) -> None:
        """그 가계부 계좌들의 해당 월 스냅샷 hard delete (upsert 재생성용).

        박제는 파생 데이터라 soft delete 대신 hard delete — DELETED 행이 안 쌓임.
        """
        stmt = delete(AccountSnapshot).where(
            AccountSnapshot.account_id.in_(
                select(Account.id).where(Account.household_id == household_id)
            ),
            AccountSnapshot.snapshot_date == month_first,
        )
        await self.db.execute(stmt)

    async def soft_delete_by_account_id(self, account_id: UUID) -> int:
        """이 통장의 스냅샷 soft-delete — 통장 cascade용.
        (월별 upsert 재생성용 delete_for_household_month 와 달리 통장 삭제 시 보존 X)"""
        stmt = (
            update(AccountSnapshot)
            .where(
                and_(
                    AccountSnapshot.account_id == account_id,
                    AccountSnapshot.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .values(data_stat_cd=DataStatus.DELETED)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def save_all(self, snapshots: list[AccountSnapshot]) -> None:
        if not snapshots:
            return
        self.db.add_all(snapshots)
        await self.db.flush()
