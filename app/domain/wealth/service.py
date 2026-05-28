"""자산 페이지 1호출 overview.

account.list_accounts + account_snapshot.get_yearly_snapshots 위임만.
종목 단건/통장 단건 상세는 별도 endpoint 유지 (`/portfolio/accounts/{id}/overview`).
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account import service as account_service
from app.domain.account_snapshot import service as account_snapshot_service
from app.domain.household.model import Household
from app.domain.wealth.schema import WealthOverviewResponse


async def get_wealth_overview(
    db: AsyncSession,
    household: Household,
    from_date: date | None,
    to_date: date | None,
) -> WealthOverviewResponse:
    accounts = await account_service.list_accounts(db, household)
    total_balance = sum((a.balance for a in accounts), Decimal("0"))

    yearly = await account_snapshot_service.get_yearly_snapshots(
        db, household, from_date, to_date,
    )

    return WealthOverviewResponse(
        total_balance=total_balance,
        accounts=accounts,
        yearly_snapshots=yearly,
    )
