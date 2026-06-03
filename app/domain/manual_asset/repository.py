from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.manual_asset.model import ManualAsset


class ManualAssetRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(self, asset_id: UUID) -> ManualAsset | None:
        result = await self.db.execute(
            select(ManualAsset).where(
                and_(
                    ManualAsset.id == asset_id,
                    ManualAsset.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_household_id(self, household_id: UUID) -> list[ManualAsset]:
        result = await self.db.execute(
            select(ManualAsset)
            .where(
                and_(
                    ManualAsset.household_id == household_id,
                    ManualAsset.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(ManualAsset.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

    async def find_active_by_account_id(self, account_id: UUID) -> list[ManualAsset]:
        result = await self.db.execute(
            select(ManualAsset)
            .where(
                and_(
                    ManualAsset.account_id == account_id,
                    ManualAsset.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(ManualAsset.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

    async def sum_valuation_by_account(self, account_id: UUID) -> Decimal:
        """current_valuation 합산 (_calc_balance roll-up 용)"""
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(ManualAsset.current_valuation), 0)
            ).where(
                and_(
                    ManualAsset.account_id == account_id,
                    ManualAsset.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return Decimal(result.scalar() or 0)

    async def sum_valuation_by_accounts(
        self, account_ids: list[UUID],
    ) -> dict[UUID, Decimal]:
        """여러 통장 수동자산 평가액 합 배치 — 계좌목록 잔액 N+1 제거용."""
        base = {aid: Decimal("0") for aid in account_ids}
        if not account_ids:
            return base
        result = await self.db.execute(
            select(
                ManualAsset.account_id,
                func.coalesce(func.sum(ManualAsset.current_valuation), 0).label("total"),
            )
            .where(
                and_(
                    ManualAsset.account_id.in_(account_ids),
                    ManualAsset.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .group_by(ManualAsset.account_id)
        )
        for account_id, total in result.all():
            base[account_id] = Decimal(total)
        return base

    async def soft_delete_by_account_id(self, account_id: UUID) -> int:
        """이 통장에 연결된 수동자산 soft-delete — 통장 cascade용."""
        stmt = (
            update(ManualAsset)
            .where(
                and_(
                    ManualAsset.account_id == account_id,
                    ManualAsset.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .values(data_stat_cd=DataStatus.DELETED)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def save(self, asset: ManualAsset) -> None:
        self.db.add(asset)
        await self.db.flush()
