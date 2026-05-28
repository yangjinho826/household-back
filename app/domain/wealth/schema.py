from app.core.schema import CamelBaseModel
from app.core.types import Money
from app.domain.account.schema import AccountResponse
from app.domain.account_snapshot.schema import SnapshotYearlyResponse


class WealthOverviewResponse(CamelBaseModel):
    """자산 페이지 진입 응답 — 통장 목록 + 연간 자산 추이"""

    total_balance: Money
    accounts: list[AccountResponse]
    yearly_snapshots: SnapshotYearlyResponse
