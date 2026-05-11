from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.core.types import Money


class SnapshotMonthBalance(BaseModel):
    account_id: UUID
    account_name: str
    balance: Money


class SnapshotMonth(BaseModel):
    snapshot_date: date
    total_balance: Money
    accounts: list[SnapshotMonthBalance]


class SnapshotYearlyResponse(BaseModel):
    months: list[SnapshotMonth]
    current_month_saved: bool
    current_month_date: date
