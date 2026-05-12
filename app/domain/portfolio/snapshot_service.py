import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.account.enum import AccountType
from app.domain.account.repository import AccountRepository
from app.domain.household.model import Household
from app.domain.portfolio.model import PortfolioValueHistory
from app.domain.portfolio.repository import (
    PortfolioItemRepository,
    PortfolioValueHistoryRepository,
)

logger = logging.getLogger(__name__)


async def snapshot_household_portfolio(
    db: AsyncSession,
    household: Household,
    snapshot_date: date,
) -> list[PortfolioValueHistory]:
    """가계부의 모든 INVESTMENT 통장 종목들을 그 시점 상태로 박제.

    호출처: account_snapshot/service.py 의 create_target_month_snapshot
    """
    account_repo = AccountRepository(db)
    item_repo = PortfolioItemRepository(db)
    history_repo = PortfolioValueHistoryRepository(db)

    accounts = await account_repo.find_active_by_household_id(household.id)
    investment_accounts = [
        a for a in accounts
        if a.account_type == AccountType.INVESTMENT and not a.is_archived
    ]

    histories: list[PortfolioValueHistory] = []
    for a in investment_accounts:
        items = await item_repo.find_active_by_account_id(a.id)
        for i in items:
            cost = i.quantity * i.avg_price
            valuation = i.quantity * i.current_price
            histories.append(
                PortfolioValueHistory(
                    household_id=household.id,
                    account_id=a.id,
                    portfolio_item_id=i.id,
                    snapshot_date=snapshot_date,
                    quantity=i.quantity,
                    avg_price=i.avg_price,
                    current_price=i.current_price,
                    cost=cost,
                    valuation=valuation,
                    data_stat_cd=DataStatus.ACTIVE,
                )
            )

    await history_repo.save_all(histories)
    logger.info(
        "종목 박제 완료 (household_id=%s, date=%s, items=%d)",
        household.id, snapshot_date, len(histories),
    )
    return histories
