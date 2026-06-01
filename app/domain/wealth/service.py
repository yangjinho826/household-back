"""자산 페이지 1호출 overview.

account.list_accounts + account_snapshot.get_yearly_snapshots 위임 + 자산군 배분 집계.
종목 단건/통장 단건 상세는 별도 endpoint 유지 (`/portfolio/accounts/{id}/overview`).
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account import service as account_service
from app.domain.account.enum import AccountType
from app.domain.account.schema import AccountResponse
from app.domain.account_snapshot import service as account_snapshot_service
from app.domain.household.model import Household
from app.domain.portfolio.enum import AssetClass
from app.domain.portfolio.model import PortfolioItem
from app.domain.portfolio.repository import PortfolioItemRepository
from app.domain.wealth.schema import (
    AllocationResponse,
    AssetClassSlice,
    WealthOverviewResponse,
)


def _build_allocation(
    accounts: list[AccountResponse], items: list[PortfolioItem],
) -> AllocationResponse:
    """현재 시점 자산군별 배분.

    - 계좌 현금은 CASH 슬라이스. INVESTMENT 통장은 cash 부분만(종목 평가액은 종목에서),
      그 외 통장은 balance 전체가 현금.
    - 종목은 asset_class 별 평가액(qty * current_price) 합산.
    """
    slices: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for a in accounts:
        if a.account_type == AccountType.INVESTMENT:
            slices[AssetClass.CASH.value] += a.cash or Decimal("0")
        else:
            slices[AssetClass.CASH.value] += a.balance

    for item in items:
        slices[item.asset_class] += item.quantity * item.current_price

    total = sum(slices.values(), Decimal("0"))
    current = [
        AssetClassSlice(
            asset_class=AssetClass(asset_class),
            valuation=valuation,
            ratio=(valuation / total * Decimal("100")) if total > 0 else Decimal("0"),
        )
        for asset_class, valuation in slices.items()
        if valuation != 0
    ]
    current.sort(key=lambda s: s.valuation, reverse=True)
    return AllocationResponse(current_allocation=current)


async def get_wealth_overview(
    db: AsyncSession,
    household: Household,
    from_date: date | None,
    to_date: date | None,
) -> WealthOverviewResponse:
    accounts = await account_service.list_accounts(db, household)
    total_balance = sum((a.balance for a in accounts), Decimal("0"))

    items = await PortfolioItemRepository(db).find_active_by_household_id(household.id)
    allocation = _build_allocation(accounts, items)

    yearly = await account_snapshot_service.get_yearly_snapshots(
        db, household, from_date, to_date,
    )

    return WealthOverviewResponse(
        total_balance=total_balance,
        accounts=accounts,
        yearly_snapshots=yearly,
        allocation=allocation,
    )
