from app.core.schema import CamelBaseModel
from app.core.types import Money, Rate
from app.domain.account.schema import AccountResponse
from app.domain.account_snapshot.schema import SnapshotYearlyResponse
from app.domain.portfolio.enum import AssetClass


class AssetClassSlice(CamelBaseModel):
    """자산 성격(asset_class) 1조각 — 배분 파이의 한 칸"""

    asset_class: AssetClass
    valuation: Money
    ratio: Rate  # 전체 대비 비중 (%, 0~100)


class AllocationResponse(CamelBaseModel):
    """자산군별 배분 — 현재 시점. (월별 추이는 R5a-3 에서 allocation_trend 추가)"""

    current_allocation: list[AssetClassSlice]


class WealthOverviewResponse(CamelBaseModel):
    """자산 페이지 진입 응답 — 통장 목록 + 연간 자산 추이 + 자산군 배분"""

    total_balance: Money
    accounts: list[AccountResponse]
    yearly_snapshots: SnapshotYearlyResponse
    allocation: AllocationResponse
