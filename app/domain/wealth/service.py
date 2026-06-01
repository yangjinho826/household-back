"""자산 페이지 1호출 overview.

account.list_accounts + account_snapshot.get_yearly_snapshots 위임 + 자산군 배분 집계.
종목 단건/통장 단건 상세는 별도 endpoint 유지 (`/portfolio/accounts/{id}/overview`).
"""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account import service as account_service
from app.domain.account.enum import AccountType
from app.domain.account.model import Account
from app.domain.account.repository import AccountRepository
from app.domain.account.schema import AccountResponse
from app.domain.account_snapshot import service as account_snapshot_service
from app.domain.account_snapshot.model import AccountSnapshot
from app.domain.account_snapshot.repository import AccountSnapshotRepository
from app.domain.household.model import Household
from app.domain.portfolio.enum import AssetClass
from app.domain.portfolio.model import PortfolioItem, PortfolioValueHistory
from app.domain.portfolio.repository import (
    PortfolioItemRepository,
    PortfolioValueHistoryRepository,
)
from app.domain.wealth.schema import (
    AllocationResponse,
    AllocationTrendPoint,
    AssetClassSlice,
    WealthOverviewResponse,
)


def _slices_to_list(slices: dict[str, Decimal]) -> list[AssetClassSlice]:
    """자산군별 누적액 dict → ratio 채운 슬라이스 리스트. 0값 제외, valuation desc."""
    total = sum(slices.values(), Decimal("0"))
    result = [
        AssetClassSlice(
            asset_class=AssetClass(asset_class),
            valuation=valuation,
            ratio=(valuation / total * Decimal("100")) if total > 0 else Decimal("0"),
        )
        for asset_class, valuation in slices.items()
        if valuation != 0
    ]
    result.sort(key=lambda s: s.valuation, reverse=True)
    return result


def _build_allocation(
    accounts: list[AccountResponse], items: list[PortfolioItem],
) -> list[AssetClassSlice]:
    """현재 시점 자산군별 배분.

    - 계좌 현금은 CASH 슬라이스. INVESTMENT 통장은 cash 부분만(종목 평가액은 종목에서),
      그 외 통장은 balance 전체가 현금.
    - 종목은 asset_class 별 평가액(qty * current_price) 합산.
    """
    slices: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for a in accounts:
        if a.account_type == AccountType.INVESTMENT:
            slices[AssetClass.CASH.value] += a.cash or Decimal("0")
        elif a.account_type == AccountType.REAL_ESTATE:
            slices[AssetClass.REAL_ESTATE.value] += a.balance
        elif a.account_type == AccountType.PENSION:
            slices[AssetClass.PENSION.value] += a.balance
        else:
            slices[AssetClass.CASH.value] += a.balance

    for item in items:
        slices[item.asset_class] += item.quantity * item.current_price

    return _slices_to_list(slices)


def build_allocation_trend(
    account_snapshots: list[AccountSnapshot],
    portfolio_histories: list[PortfolioValueHistory],
    accounts: list[Account],
) -> list[AllocationTrendPoint]:
    """월별 자산군 배분추이 — 박제된 AccountSnapshot + PortfolioValueHistory 재구성.

    - 종목: PVH 의 박제 시점 asset_class 별 valuation 합 (과거 재분류 영향 없음).
    - INVESTMENT 계좌 현금: AccountSnapshot.balance − 그 계좌 그달 PVH valuation 합
      (`_calc_balance` 의 balance = cash + valuation 등식 역산).
    - 그 외 계좌(LIVING/SAVINGS/OTHER): balance 전체가 CASH.
    - REAL_ESTATE/PENSION 전용계좌: balance 가 그달 평가액(roll-up 박제값).
    """
    account_type_map = {a.id: a.account_type for a in accounts}

    # (월, 계좌)별 종목 평가액 합 — INVESTMENT cash 역산용
    pvh_by_account: dict[tuple[date, uuid.UUID], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    trend: dict[date, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )

    for h in portfolio_histories:
        pvh_by_account[(h.snapshot_date, h.account_id)] += h.valuation
        trend[h.snapshot_date][h.asset_class] += h.valuation

    for s in account_snapshots:
        account_type = account_type_map.get(s.account_id)
        month = trend[s.snapshot_date]
        if account_type == AccountType.REAL_ESTATE:
            month[AssetClass.REAL_ESTATE.value] += s.balance
        elif account_type == AccountType.PENSION:
            month[AssetClass.PENSION.value] += s.balance
        elif account_type == AccountType.INVESTMENT:
            cash = s.balance - pvh_by_account[(s.snapshot_date, s.account_id)]
            month[AssetClass.CASH.value] += cash
        else:
            month[AssetClass.CASH.value] += s.balance

    return [
        AllocationTrendPoint(snapshot_date=d, slices=_slices_to_list(slices))
        for d, slices in sorted(trend.items(), key=lambda kv: kv[0])
    ]


async def get_wealth_overview(
    db: AsyncSession,
    household: Household,
    from_date: date | None,
    to_date: date | None,
) -> WealthOverviewResponse:
    accounts = await account_service.list_accounts(db, household)
    total_balance = sum((a.balance for a in accounts), Decimal("0"))

    items = await PortfolioItemRepository(db).find_active_by_household_id(household.id)
    current_allocation = _build_allocation(accounts, items)

    # 월별 배분추이 — 박제된 스냅샷 재구성 (yearly_snapshots 와 동일 범위)
    from_resolved, to_resolved = account_snapshot_service.resolve_snapshot_range(
        from_date, to_date,
    )
    account_snapshots = await AccountSnapshotRepository(db).find_by_household_and_range(
        household.id, from_resolved, to_resolved,
    )
    portfolio_histories = await PortfolioValueHistoryRepository(
        db
    ).find_by_household_and_range(household.id, from_resolved, to_resolved)
    snapshot_account_ids = list({s.account_id for s in account_snapshots})
    snapshot_accounts = await AccountRepository(db).find_by_ids(snapshot_account_ids)
    allocation = AllocationResponse(
        current_allocation=current_allocation,
        allocation_trend=build_allocation_trend(
            account_snapshots, portfolio_histories, snapshot_accounts,
        ),
    )

    yearly = await account_snapshot_service.get_yearly_snapshots(
        db, household, from_date, to_date,
    )

    return WealthOverviewResponse(
        total_balance=total_balance,
        accounts=accounts,
        yearly_snapshots=yearly,
        allocation=allocation,
    )
