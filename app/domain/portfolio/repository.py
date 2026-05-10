from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.portfolio.enum import PortfolioTxType
from app.domain.portfolio.model import PortfolioItem, PortfolioTransaction


class PortfolioItemRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(self, item_id: UUID) -> PortfolioItem | None:
        result = await self.db.execute(
            select(PortfolioItem).where(
                and_(
                    PortfolioItem.id == item_id,
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_household_id(self, household_id: UUID) -> list[PortfolioItem]:
        result = await self.db.execute(
            select(PortfolioItem)
            .where(
                and_(
                    PortfolioItem.household_id == household_id,
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(PortfolioItem.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

    async def find_active_by_account_id(self, account_id: UUID) -> list[PortfolioItem]:
        result = await self.db.execute(
            select(PortfolioItem)
            .where(
                and_(
                    PortfolioItem.account_id == account_id,
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(PortfolioItem.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

    async def find_active_by_account_and_ticker(
        self, account_id: UUID, ticker: str,
    ) -> PortfolioItem | None:
        """누적 매수 시 같은 종목 있는지 확인"""
        result = await self.db.execute(
            select(PortfolioItem).where(
                and_(
                    PortfolioItem.account_id == account_id,
                    PortfolioItem.ticker == ticker,
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def sum_valuation_by_account(self, account_id: UUID) -> Decimal:
        """qty * current_price 합산 (_calc_balance 용)"""
        result = await self.db.execute(
            select(func.coalesce(func.sum(PortfolioItem.quantity * PortfolioItem.current_price), 0)).where(
                and_(
                    PortfolioItem.account_id == account_id,
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return Decimal(result.scalar() or 0)

    async def save(self, item: PortfolioItem) -> None:
        self.db.add(item)
        await self.db.flush()


class PortfolioTransactionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_active_by_household_id(self, household_id: UUID) -> list[PortfolioTransaction]:
        result = await self.db.execute(
            select(PortfolioTransaction)
            .where(
                and_(
                    PortfolioTransaction.household_id == household_id,
                    PortfolioTransaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(PortfolioTransaction.tx_date.desc(), PortfolioTransaction.frst_reg_dt.desc())
        )
        return list(result.scalars().all())

    async def find_active_by_account_id(self, account_id: UUID) -> list[PortfolioTransaction]:
        result = await self.db.execute(
            select(PortfolioTransaction)
            .where(
                and_(
                    PortfolioTransaction.account_id == account_id,
                    PortfolioTransaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(PortfolioTransaction.tx_date.desc(), PortfolioTransaction.frst_reg_dt.desc())
        )
        return list(result.scalars().all())

    async def sum_for_account(self, account_id: UUID) -> dict[str, Decimal]:
        """통장별 BUY/SELL 합산 — 단가 * 수량 (_calc_balance 용)"""
        result = await self.db.execute(
            select(
                PortfolioTransaction.pt_type,
                func.coalesce(
                    func.sum(PortfolioTransaction.quantity * PortfolioTransaction.price), 0
                ).label("total"),
            )
            .where(
                and_(
                    PortfolioTransaction.account_id == account_id,
                    PortfolioTransaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .group_by(PortfolioTransaction.pt_type)
        )
        sums = {"buy": Decimal("0"), "sell": Decimal("0")}
        for pt_type, total in result.all():
            if pt_type == PortfolioTxType.BUY:
                sums["buy"] = Decimal(total)
            elif pt_type == PortfolioTxType.SELL:
                sums["sell"] = Decimal(total)
        return sums

    async def save(self, tx: PortfolioTransaction) -> None:
        self.db.add(tx)
        await self.db.flush()
