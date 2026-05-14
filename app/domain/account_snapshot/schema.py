from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.core.types import Money


class SnapshotMonthBalance(BaseModel):
    account_id: UUID
    account_name: str
    balance: Money
    monthly_income: Money
    monthly_expense: Money
    monthly_fixed_expense: Money


class SnapshotMonth(BaseModel):
    snapshot_date: date
    total_balance: Money
    total_income: Money
    total_expense: Money
    total_fixed_expense: Money
    accounts: list[SnapshotMonthBalance]


class SnapshotYearlyResponse(BaseModel):
    months: list[SnapshotMonth]
    target_month_saved: bool
    target_month_date: date
