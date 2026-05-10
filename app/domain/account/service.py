import logging
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.domain.account.enum import AccountType
from app.domain.account.model import Account
from app.domain.account.repository import AccountRepository
from app.domain.account.schema import (
    AccountCreateRequest,
    AccountResponse,
    AccountUpdateRequest,
)
from app.domain.household.model import Household
from app.domain.portfolio.repository import (
    PortfolioItemRepository,
    PortfolioTransactionRepository,
)
from app.domain.transaction.repository import TransactionRepository

logger = logging.getLogger(__name__)


@dataclass
class BalanceSummary:
    """통장별 잔액 + (INVESTMENT 한정) portfolio 요약"""

    balance: Decimal
    cash: Decimal | None = None
    portfolio_cost: Decimal | None = None
    portfolio_valuation: Decimal | None = None
    portfolio_profit_loss: Decimal | None = None
    portfolio_profit_loss_rate: Decimal | None = None


async def _calc_balance(
    tx_repo: TransactionRepository, account: Account, db: AsyncSession,
) -> BalanceSummary:
    """통장 balance 계산. INVESTMENT 통장이면 portfolio summary 도 같이 반환."""
    sums = await tx_repo.sum_for_account(account.id)
    cash = (
        account.start_balance
        + sums["income"]
        - sums["expense"]
        - sums["transfer_out"]
        + sums["transfer_in"]
    )

    if account.account_type != AccountType.INVESTMENT:
        return BalanceSummary(balance=cash)

    # INVESTMENT 통장 — portfolio_transactions + portfolio 평가금 합산
    pt_repo = PortfolioTransactionRepository(db)
    pi_repo = PortfolioItemRepository(db)

    pt_sums = await pt_repo.sum_for_account(account.id)
    cash -= pt_sums["buy"]
    cash += pt_sums["sell"]

    items = await pi_repo.find_active_by_account_id(account.id)
    cost = sum((i.quantity * i.avg_price for i in items), Decimal("0"))
    valuation = sum((i.quantity * i.current_price for i in items), Decimal("0"))
    profit_loss = valuation - cost
    profit_loss_rate = (profit_loss / cost * Decimal("100")) if cost > 0 else Decimal("0")
    balance = cash + valuation

    return BalanceSummary(
        balance=balance,
        cash=cash,
        portfolio_cost=cost,
        portfolio_valuation=valuation,
        portfolio_profit_loss=profit_loss,
        portfolio_profit_loss_rate=profit_loss_rate,
    )


def _build_response(account: Account, summary: BalanceSummary) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        household_id=account.household_id,
        name=account.name,
        account_type=account.account_type,
        start_balance=account.start_balance,
        balance=summary.balance,
        color=account.color,
        icon=account.icon,
        sort_order=account.sort_order,
        is_archived=account.is_archived,
        cash=summary.cash,
        portfolio_cost=summary.portfolio_cost,
        portfolio_valuation=summary.portfolio_valuation,
        portfolio_profit_loss=summary.portfolio_profit_loss,
        portfolio_profit_loss_rate=summary.portfolio_profit_loss_rate,
    )


async def list_accounts(db: AsyncSession, household: Household) -> list[AccountResponse]:
    repo = AccountRepository(db)
    tx_repo = TransactionRepository(db)
    accounts = await repo.find_active_by_household_id(household.id)
    responses = []
    for a in accounts:
        summary = await _calc_balance(tx_repo, a, db)
        responses.append(_build_response(a, summary))
    return responses


async def create_account(
    db: AsyncSession, household: Household, req: AccountCreateRequest,
) -> AccountResponse:
    repo = AccountRepository(db)
    sort_order = req.sort_order if req.sort_order is not None else (await repo.max_sort_order(household.id)) + 1

    account = Account(
        household_id=household.id,
        name=req.name.strip(),
        account_type=req.account_type,
        start_balance=req.start_balance,
        color=req.color,
        icon=req.icon,
        sort_order=sort_order,
        is_archived=False,
        data_stat_cd=DataStatus.ACTIVE,
    )
    await repo.save(account)
    logger.info("통장 생성 (account_id=%s, household_id=%s)", account.id, household.id)
    # 갓 생성: 거래/portfolio 0건이라 balance == start_balance
    summary = BalanceSummary(balance=account.start_balance)
    if account.account_type == AccountType.INVESTMENT:
        zero = Decimal("0")
        summary = BalanceSummary(
            balance=account.start_balance,
            cash=account.start_balance,
            portfolio_cost=zero,
            portfolio_valuation=zero,
            portfolio_profit_loss=zero,
            portfolio_profit_loss_rate=zero,
        )
    return _build_response(account, summary)


async def update_account(
    db: AsyncSession, household: Household, account_id: UUID, req: AccountUpdateRequest,
) -> AccountResponse:
    repo = AccountRepository(db)
    account = await repo.find_by_id(account_id)
    if not account or account.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    if req.name is not None:
        account.name = req.name.strip()
    if req.account_type is not None:
        account.account_type = req.account_type
    if req.start_balance is not None:
        account.start_balance = req.start_balance
    if req.color is not None:
        account.color = req.color
    if req.icon is not None:
        account.icon = req.icon
    if req.sort_order is not None:
        account.sort_order = req.sort_order
    if req.is_archived is not None:
        account.is_archived = req.is_archived

    await db.flush()
    tx_repo = TransactionRepository(db)
    summary = await _calc_balance(tx_repo, account, db)
    return _build_response(account, summary)


async def delete_account(
    db: AsyncSession, household: Household, account_id: UUID,
) -> None:
    repo = AccountRepository(db)
    account = await repo.find_by_id(account_id)
    if not account or account.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    account.data_stat_cd = DataStatus.DELETED
    await db.flush()
    logger.info("통장 삭제 (account_id=%s)", account_id)
