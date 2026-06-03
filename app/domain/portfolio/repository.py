from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.portfolio.enum import Market, PortfolioTxType
from app.domain.portfolio.model import (
    PortfolioItem,
    PortfolioTransaction,
    PortfolioValueHistory,
)


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

    async def find_by_id_any_status(self, item_id: UUID) -> PortfolioItem | None:
        """삭제 상태 무관 조회 — 전량매도로 죽은 종목의 거래 수정/삭제 재계산용."""
        result = await self.db.execute(
            select(PortfolioItem).where(PortfolioItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def find_active_by_account_ids(
        self, account_ids: list[UUID],
    ) -> dict[UUID, list[PortfolioItem]]:
        """여러 통장 보유종목 배치 — 계좌목록 잔액 N+1 제거용."""
        base: dict[UUID, list[PortfolioItem]] = {aid: [] for aid in account_ids}
        if not account_ids:
            return base
        result = await self.db.execute(
            select(PortfolioItem).where(
                and_(
                    PortfolioItem.account_id.in_(account_ids),
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        for item in result.scalars().all():
            base[item.account_id].append(item)
        return base

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

    async def count_active_by_household_id(self, household_id: UUID) -> int:
        """settings overview 종목 카운트용"""
        result = await self.db.execute(
            select(func.count(PortfolioItem.id)).where(
                and_(
                    PortfolioItem.household_id == household_id,
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar() or 0

    async def count_active_by_account_id(self, account_id: UUID) -> int:
        """통장 삭제 가드용 — 이 통장에 연결된 활성 종목 수"""
        result = await self.db.execute(
            select(func.count(PortfolioItem.id)).where(
                and_(
                    PortfolioItem.account_id == account_id,
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar() or 0

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

    async def find_active_by_account_market_code(
        self, account_id: UUID, market: str, code: str,
    ) -> PortfolioItem | None:
        """누적 매수 시 같은 종목 있는지 확인 — (account, market, code) 기준"""
        result = await self.db.execute(
            select(PortfolioItem).where(
                and_(
                    PortfolioItem.account_id == account_id,
                    PortfolioItem.market == market,
                    PortfolioItem.code == code,
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_by_ids_including_deleted(self, item_ids: list[UUID]) -> list[PortfolioItem]:
        """삭제된 종목까지 포함 fetch (value-history 응답에 ticker 표시용)"""
        if not item_ids:
            return []
        result = await self.db.execute(
            select(PortfolioItem).where(PortfolioItem.id.in_(item_ids))
        )
        return list(result.scalars().all())

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

    async def find_active_distinct_code_market_by_markets(
        self, markets: list[Market],
    ) -> list[tuple[str, Market]]:
        """전 가계부 통틀어 (code, market) DISTINCT 추출 — 시세 갱신 야후 호출 단위.
        is_archived 종목은 제외 (보관된 종목 시세 갱신 불필요)."""
        result = await self.db.execute(
            select(PortfolioItem.code, PortfolioItem.market)
            .where(
                and_(
                    PortfolioItem.market.in_([m.value for m in markets]),
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                    PortfolioItem.is_archived.is_(False),
                )
            )
            .distinct()
        )
        return [(code, Market(market)) for code, market in result.all()]

    async def find_active_distinct_code_market_by_household_and_markets(
        self, household_id: UUID, markets: list[Market],
    ) -> list[tuple[str, Market]]:
        """특정 가계부가 보유한 (code, market) DISTINCT — 수동 시세 갱신 야후 호출 단위.
        가격 자체는 시장 공통이라 bulk update 는 전 가계부에 적용되지만, fetch 대상은
        이 가계부 보유 종목으로 한정해 야후 호출을 최소화한다."""
        result = await self.db.execute(
            select(PortfolioItem.code, PortfolioItem.market)
            .where(
                and_(
                    PortfolioItem.household_id == household_id,
                    PortfolioItem.market.in_([m.value for m in markets]),
                    PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                    PortfolioItem.is_archived.is_(False),
                )
            )
            .distinct()
        )
        return [(code, Market(market)) for code, market in result.all()]

    async def bulk_update_current_price_by_code_market(
        self, prices: dict[tuple[str, Market], Decimal],
    ) -> int:
        """매치되는 모든 active row 의 current_price 일괄 update.
        반환: 총 영향받은 row 수."""
        if not prices:
            return 0
        total = 0
        for (code, market), price in prices.items():
            result = await self.db.execute(
                update(PortfolioItem)
                .where(
                    and_(
                        PortfolioItem.code == code,
                        PortfolioItem.market == market.value,
                        PortfolioItem.data_stat_cd == DataStatus.ACTIVE,
                    )
                )
                .values(current_price=price)
            )
            total += result.rowcount or 0
        return total


class PortfolioTransactionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(self, tx_id: UUID) -> PortfolioTransaction | None:
        result = await self.db.execute(
            select(PortfolioTransaction).where(
                and_(
                    PortfolioTransaction.id == tx_id,
                    PortfolioTransaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_item_id(self, item_id: UUID) -> list[PortfolioTransaction]:
        """종목의 모든 활성 거래 — 재계산용"""
        result = await self.db.execute(
            select(PortfolioTransaction)
            .where(
                and_(
                    PortfolioTransaction.portfolio_item_id == item_id,
                    PortfolioTransaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(PortfolioTransaction.tx_date.asc(), PortfolioTransaction.frst_reg_dt.asc())
        )
        return list(result.scalars().all())

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

    async def sum_for_accounts(
        self, account_ids: list[UUID],
    ) -> dict[UUID, dict[str, Decimal]]:
        """여러 통장 BUY/SELL 합산 배치 — 계좌목록 잔액 N+1 제거용."""
        base = {
            aid: {"buy": Decimal("0"), "sell": Decimal("0")} for aid in account_ids
        }
        if not account_ids:
            return base
        result = await self.db.execute(
            select(
                PortfolioTransaction.account_id,
                PortfolioTransaction.pt_type,
                func.coalesce(
                    func.sum(PortfolioTransaction.quantity * PortfolioTransaction.price), 0
                ).label("total"),
            )
            .where(
                and_(
                    PortfolioTransaction.account_id.in_(account_ids),
                    PortfolioTransaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .group_by(
                PortfolioTransaction.account_id, PortfolioTransaction.pt_type,
            )
        )
        for account_id, pt_type, total in result.all():
            if pt_type == PortfolioTxType.BUY:
                base[account_id]["buy"] = Decimal(total)
            elif pt_type == PortfolioTxType.SELL:
                base[account_id]["sell"] = Decimal(total)
        return base

    async def save(self, tx: PortfolioTransaction) -> None:
        self.db.add(tx)
        await self.db.flush()

    async def soft_delete_by_account_id(self, account_id: UUID) -> int:
        """이 통장의 종목 매매이력 soft-delete — 통장 cascade용(전량매도 후 잔존분)."""
        stmt = (
            update(PortfolioTransaction)
            .where(
                and_(
                    PortfolioTransaction.account_id == account_id,
                    PortfolioTransaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .values(data_stat_cd=DataStatus.DELETED)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def find_sell_txs_by_item(
        self, item_id: UUID, from_date: date, to_date: date,
    ) -> list[PortfolioTransaction]:
        """종목의 기간 내 매도 거래 — 매매손익 집계용. 최신순."""
        result = await self.db.execute(
            select(PortfolioTransaction)
            .where(
                and_(
                    PortfolioTransaction.portfolio_item_id == item_id,
                    PortfolioTransaction.pt_type == PortfolioTxType.SELL,
                    PortfolioTransaction.data_stat_cd == DataStatus.ACTIVE,
                    PortfolioTransaction.tx_date >= from_date,
                    PortfolioTransaction.tx_date <= to_date,
                )
            )
            .order_by(
                PortfolioTransaction.tx_date.desc(),
                PortfolioTransaction.frst_reg_dt.desc(),
            )
        )
        return list(result.scalars().all())

    async def find_sell_txs_by_account(
        self, account_id: UUID, household_id: UUID, from_date: date, to_date: date,
    ) -> list[PortfolioTransaction]:
        """계좌의 기간 내 매도 거래 — 계좌 누적 매매손익 집계용. 최신순.

        전량매도로 종목(item)이 soft delete 돼도 매도 거래는 ACTIVE 로 남아 포함된다.
        household_id 를 함께 걸어 소유권을 보장(남의 계좌 id 면 빈 결과).
        """
        result = await self.db.execute(
            select(PortfolioTransaction)
            .where(
                and_(
                    PortfolioTransaction.account_id == account_id,
                    PortfolioTransaction.household_id == household_id,
                    PortfolioTransaction.pt_type == PortfolioTxType.SELL,
                    PortfolioTransaction.data_stat_cd == DataStatus.ACTIVE,
                    PortfolioTransaction.tx_date >= from_date,
                    PortfolioTransaction.tx_date <= to_date,
                )
            )
            .order_by(
                PortfolioTransaction.tx_date.desc(),
                PortfolioTransaction.frst_reg_dt.desc(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def _cursor_after(cursor: str | None):
        """tx_date DESC, id DESC 정렬 기준 cursor 조건 — transaction 패턴 그대로"""
        if not cursor:
            return None
        try:
            date_str, id_str = cursor.split("|", 1)
            cur_date = date.fromisoformat(date_str)
            cur_id = UUID(id_str)
        except (ValueError, AttributeError):
            return None
        return or_(
            PortfolioTransaction.tx_date < cur_date,
            and_(
                PortfolioTransaction.tx_date == cur_date,
                PortfolioTransaction.id < cur_id,
            ),
        )

    async def list_active_by_item_id_cursor(
        self, item_id: UUID, cursor: str | None, limit: int,
    ) -> list[PortfolioTransaction]:
        """종목 단건 거래 내역 — 무한 스크롤. limit+1 로 has_next 판정."""
        conds = [
            PortfolioTransaction.portfolio_item_id == item_id,
            PortfolioTransaction.data_stat_cd == DataStatus.ACTIVE,
        ]
        cursor_cond = self._cursor_after(cursor)
        if cursor_cond is not None:
            conds.append(cursor_cond)
        result = await self.db.execute(
            select(PortfolioTransaction)
            .where(and_(*conds))
            .order_by(
                PortfolioTransaction.tx_date.desc(),
                PortfolioTransaction.id.desc(),
            )
            .limit(limit + 1)
        )
        return list(result.scalars().all())


class PortfolioValueHistoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save_all(self, histories: list[PortfolioValueHistory]) -> None:
        if not histories:
            return
        self.db.add_all(histories)
        await self.db.flush()

    async def soft_delete_by_account_id(self, account_id: UUID) -> int:
        """이 통장의 종목 가치 박제 soft-delete — 통장 cascade용."""
        stmt = (
            update(PortfolioValueHistory)
            .where(
                and_(
                    PortfolioValueHistory.account_id == account_id,
                    PortfolioValueHistory.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .values(data_stat_cd=DataStatus.DELETED)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def delete_for_household_month(
        self, household_id: UUID, snapshot_date: date,
    ) -> None:
        """그 가계부의 해당 월 종목 박제 hard delete (upsert 재생성용)."""
        stmt = delete(PortfolioValueHistory).where(
            and_(
                PortfolioValueHistory.household_id == household_id,
                PortfolioValueHistory.snapshot_date == snapshot_date,
            )
        )
        await self.db.execute(stmt)

    async def has_active_for_month(self, household_id: UUID, month_date: date) -> bool:
        """이번 달에 종목 박제됐는지 (account_snapshot 과 동일 패턴)"""
        result = await self.db.execute(
            select(func.count(PortfolioValueHistory.id)).where(
                and_(
                    PortfolioValueHistory.household_id == household_id,
                    PortfolioValueHistory.snapshot_date == month_date,
                    PortfolioValueHistory.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return (result.scalar_one() or 0) > 0

    async def find_by_account_and_range(
        self, account_id: UUID, from_date: date, to_date: date,
    ) -> list[PortfolioValueHistory]:
        result = await self.db.execute(
            select(PortfolioValueHistory)
            .where(
                and_(
                    PortfolioValueHistory.account_id == account_id,
                    PortfolioValueHistory.snapshot_date >= from_date,
                    PortfolioValueHistory.snapshot_date <= to_date,
                    PortfolioValueHistory.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(
                PortfolioValueHistory.portfolio_item_id.asc(),
                PortfolioValueHistory.snapshot_date.asc(),
            )
        )
        return list(result.scalars().all())

    async def find_by_household_and_range(
        self, household_id: UUID, from_date: date, to_date: date,
    ) -> list[PortfolioValueHistory]:
        """가계부 전체 종목 박제 — 월별 자산군 배분추이 집계용."""
        result = await self.db.execute(
            select(PortfolioValueHistory)
            .where(
                and_(
                    PortfolioValueHistory.household_id == household_id,
                    PortfolioValueHistory.snapshot_date >= from_date,
                    PortfolioValueHistory.snapshot_date <= to_date,
                    PortfolioValueHistory.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(PortfolioValueHistory.snapshot_date.asc())
        )
        return list(result.scalars().all())

    async def find_by_item_and_range(
        self, item_id: UUID, from_date: date, to_date: date,
    ) -> list[PortfolioValueHistory]:
        result = await self.db.execute(
            select(PortfolioValueHistory)
            .where(
                and_(
                    PortfolioValueHistory.portfolio_item_id == item_id,
                    PortfolioValueHistory.snapshot_date >= from_date,
                    PortfolioValueHistory.snapshot_date <= to_date,
                    PortfolioValueHistory.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .order_by(PortfolioValueHistory.snapshot_date.asc())
        )
        return list(result.scalars().all())
