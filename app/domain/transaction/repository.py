from calendar import monthrange
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.transaction.enum import TxType
from app.domain.transaction.model import Transaction


class TransactionFilter:
    def __init__(
        self,
        tx_type: TxType | None = None,
        account_id: UUID | None = None,
        category_id: UUID | None = None,
        year: int | None = None,
        month: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> None:
        self.tx_type = tx_type
        self.account_id = account_id
        self.category_id = category_id
        # year + month → from/to 자동 변환
        if year is not None and month is not None:
            self.from_date = date(year, month, 1)
            self.to_date = date(year, month, monthrange(year, month)[1])
        else:
            self.from_date = from_date
            self.to_date = to_date


class TransactionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(self, tx_id: UUID) -> Transaction | None:
        result = await self.db.execute(
            select(Transaction).where(
                and_(
                    Transaction.id == tx_id,
                    Transaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    def _build_conditions(self, household_id: UUID, f: TransactionFilter):
        conds = [
            Transaction.household_id == household_id,
            Transaction.data_stat_cd == DataStatus.ACTIVE,
        ]
        if f.tx_type is not None:
            conds.append(Transaction.tx_type == f.tx_type)
        if f.account_id is not None:
            conds.append(
                or_(
                    Transaction.account_id == f.account_id,
                    Transaction.to_account_id == f.account_id,
                )
            )
        if f.category_id is not None:
            conds.append(Transaction.category_id == f.category_id)
        if f.from_date is not None:
            conds.append(Transaction.tx_date >= f.from_date)
        if f.to_date is not None:
            conds.append(Transaction.tx_date <= f.to_date)
        return conds

    @staticmethod
    def _cursor_after(cursor: str | None):
        if not cursor:
            return None
        try:
            date_str, id_str = cursor.split("|", 1)
            cur_date = date.fromisoformat(date_str)
            cur_id = UUID(id_str)
        except (ValueError, AttributeError):
            return None
        return or_(
            Transaction.tx_date < cur_date,
            and_(Transaction.tx_date == cur_date, Transaction.id < cur_id),
        )

    async def list_by_cursor(
        self,
        household_id: UUID,
        f: TransactionFilter,
        cursor: str | None,
        limit: int,
    ) -> list[Transaction]:
        conds = self._build_conditions(household_id, f)
        cursor_cond = self._cursor_after(cursor)
        if cursor_cond is not None:
            conds.append(cursor_cond)
        result = await self.db.execute(
            select(Transaction)
            .where(and_(*conds))
            .order_by(Transaction.tx_date.desc(), Transaction.id.desc())
            .limit(limit + 1)
        )
        return list(result.scalars().all())

    async def count(self, household_id: UUID, f: TransactionFilter) -> int:
        conds = self._build_conditions(household_id, f)
        result = await self.db.execute(
            select(func.count(Transaction.id)).where(and_(*conds))
        )
        return result.scalar() or 0

    async def sum_for_account(self, account_id: UUID) -> dict[str, Decimal]:
        """통장별 거래 합계 — balance 계산용"""
        result = await self.db.execute(
            select(
                Transaction.tx_type,
                Transaction.account_id,
                Transaction.to_account_id,
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                and_(
                    Transaction.data_stat_cd == DataStatus.ACTIVE,
                    or_(
                        Transaction.account_id == account_id,
                        Transaction.to_account_id == account_id,
                    ),
                )
            )
            .group_by(
                Transaction.tx_type,
                Transaction.account_id,
                Transaction.to_account_id,
            )
        )

        sums = {
            "income": Decimal("0"),
            "expense": Decimal("0"),
            "transfer_out": Decimal("0"),
            "transfer_in": Decimal("0"),
        }
        for tx_type, acc_id, to_acc_id, total in result.all():
            if tx_type == TxType.INCOME and acc_id == account_id:
                sums["income"] += total
            elif (
                tx_type in (TxType.EXPENSE, TxType.FIXED_EXPENSE)
                and acc_id == account_id
            ):
                sums["expense"] += total
            elif tx_type == TxType.TRANSFER:
                if acc_id == account_id:
                    sums["transfer_out"] += total
                if to_acc_id == account_id:
                    sums["transfer_in"] += total
        return sums

    async def sum_by_category_for_month(
        self, household_id: UUID, year: int, month: int,
    ) -> list[tuple[UUID, Decimal]]:
        """category_id 별 EXPENSE/INCOME 합계 (TRANSFER 는 category_id 없음)"""
        stmt = (
            select(
                Transaction.category_id,
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
            )
            .where(
                and_(
                    Transaction.household_id == household_id,
                    func.extract("year", Transaction.tx_date) == year,
                    func.extract("month", Transaction.tx_date) == month,
                    Transaction.category_id.is_not(None),
                    Transaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .group_by(Transaction.category_id)
        )
        result = await self.db.execute(stmt)
        return [(row[0], Decimal(row[1])) for row in result.all()]

    async def sum_by_fixed_for_month(
        self, household_id: UUID, year: int, month: int,
    ) -> list[tuple[UUID, Decimal]]:
        """fixed_expense_id 별 해당 월 지출 합계 — 고정지출별 누적 사용액.

        EXPENSE 와 FIXED_EXPENSE 둘 다 포함 (기존 EXPENSE+fixed_expense_id 호환).
        """
        stmt = (
            select(
                Transaction.fixed_expense_id,
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
            )
            .where(
                and_(
                    Transaction.household_id == household_id,
                    func.extract("year", Transaction.tx_date) == year,
                    func.extract("month", Transaction.tx_date) == month,
                    Transaction.fixed_expense_id.is_not(None),
                    Transaction.tx_type.in_(
                        [TxType.EXPENSE, TxType.FIXED_EXPENSE]
                    ),
                    Transaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .group_by(Transaction.fixed_expense_id)
        )
        result = await self.db.execute(stmt)
        return [(row[0], Decimal(row[1])) for row in result.all()]

    async def sum_by_type_for_month(
        self, household_id: UUID, year: int, month: int,
    ) -> dict[str, Decimal]:
        """tx_type 별 월 합계 (income/expense/transfer)"""
        stmt = (
            select(
                Transaction.tx_type,
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
            )
            .where(
                and_(
                    Transaction.household_id == household_id,
                    func.extract("year", Transaction.tx_date) == year,
                    func.extract("month", Transaction.tx_date) == month,
                    Transaction.data_stat_cd == DataStatus.ACTIVE,
                )
            )
            .group_by(Transaction.tx_type)
        )
        result = await self.db.execute(stmt)
        sums = {
            "income": Decimal("0.00"),
            "expense": Decimal("0.00"),
            "transfer": Decimal("0.00"),
        }
        for tx_type, total in result.all():
            if tx_type == TxType.INCOME:
                sums["income"] = Decimal(total)
            elif tx_type in (TxType.EXPENSE, TxType.FIXED_EXPENSE):
                sums["expense"] += Decimal(total)
            elif tx_type == TxType.TRANSFER:
                sums["transfer"] = Decimal(total)
        return sums

    async def save(self, tx: Transaction) -> None:
        self.db.add(tx)
        await self.db.flush()

    async def daily_sums_for_month(
        self, household_id: UUID, year: int, month: int,
    ) -> list[tuple[date, str, Decimal, int]]:
        """일별 (tx_date, tx_type) 별 SUM(amount) + COUNT — 달력 뷰용"""
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        result = await self.db.execute(
            select(
                Transaction.tx_date,
                Transaction.tx_type,
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
                func.count(Transaction.id).label("cnt"),
            )
            .where(
                and_(
                    Transaction.household_id == household_id,
                    Transaction.data_stat_cd == DataStatus.ACTIVE,
                    Transaction.tx_date >= first_day,
                    Transaction.tx_date <= last_day,
                )
            )
            .group_by(Transaction.tx_date, Transaction.tx_type)
            .order_by(Transaction.tx_date.asc())
        )
        return [
            (row.tx_date, row.tx_type, Decimal(row.total), int(row.cnt))
            for row in result.all()
        ]
