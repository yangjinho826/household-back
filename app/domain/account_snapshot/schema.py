from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class SnapshotMonthBalance(BaseModel):
    account_id: UUID
    account_name: str
    balance: Decimal


class SnapshotMonth(BaseModel):
    snapshot_date: date
    total_balance: Decimal
    accounts: list[SnapshotMonthBalance]


class SnapshotYearlyResponse(BaseModel):
    months: list[SnapshotMonth]
    current_month_saved: bool
    current_month_date: date
