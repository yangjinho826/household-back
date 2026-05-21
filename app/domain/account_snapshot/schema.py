from datetime import date
from uuid import UUID

from app.core.schema import CamelBaseModel
from app.core.types import Money


class SnapshotYearlyQuery(CamelBaseModel):
    """월별 자산 추이 조회 쿼리. CamelBaseModel 이라 fromDate/toDate 로 옴."""

    from_date: date | None = None
    to_date: date | None = None


class SnapshotMonthBalance(CamelBaseModel):
    account_id: UUID
    account_name: str
    balance: Money
    monthly_income: Money
    monthly_expense: Money
    monthly_fixed_expense: Money


class SnapshotMonth(CamelBaseModel):
    snapshot_date: date
    total_balance: Money
    total_income: Money
    total_expense: Money
    total_fixed_expense: Money
    accounts: list[SnapshotMonthBalance]


class SnapshotYearlyResponse(CamelBaseModel):
    months: list[SnapshotMonth]
    target_month_saved: bool
    target_month_date: date
