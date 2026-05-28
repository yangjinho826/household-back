"""설정 페이지 1호출 overview — counts 만.

list 호출이 아니라 SELECT COUNT(*) 5번. household list 는 별도 endpoint 유지.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account.repository import AccountRepository
from app.domain.category.repository import CategoryRepository
from app.domain.fixed.repository import FixedRepository
from app.domain.household.model import Household
from app.domain.portfolio.repository import PortfolioItemRepository
from app.domain.settings.schema import SettingsOverviewResponse
from app.domain.transaction.repository import TransactionFilter, TransactionRepository


async def get_settings_overview(
    db: AsyncSession, household: Household,
) -> SettingsOverviewResponse:
    account_count = await AccountRepository(db).count_search(household.id)
    category_count = await CategoryRepository(db).count_search(household.id)
    fixed_count = await FixedRepository(db).count_search(household.id)
    transaction_count = await TransactionRepository(db).count(
        household.id, TransactionFilter(),
    )
    portfolio_count = await PortfolioItemRepository(db).count_active_by_household_id(
        household.id,
    )

    return SettingsOverviewResponse(
        account_count=account_count,
        category_count=category_count,
        fixed_count=fixed_count,
        transaction_count=transaction_count,
        portfolio_count=portfolio_count,
    )
