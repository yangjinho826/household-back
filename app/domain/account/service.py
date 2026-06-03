import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.core.pagination import CursorPage
from app.domain.account.enum import MANUAL_ASSET_ACCOUNT_TYPES, AccountType
from app.domain.account.model import Account
from app.domain.account.repository import AccountRepository
from app.domain.account.schema import (
    AccountCreateRequest,
    AccountMonthlyFlow,
    AccountReportResponse,
    AccountResponse,
    AccountUpdateRequest,
)
from app.domain.account_snapshot.repository import AccountSnapshotRepository
from app.domain.household.model import Household
from app.domain.manual_asset.repository import ManualAssetRepository
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
    # 수동자산 전용계좌(부동산·연금·금) — balance = 평가액 합 + 이체순액.
    # 이체로 납입/회수가 잔액에 반영된다(지출/수입은 거래검증에서 차단).
    if account.account_type in MANUAL_ASSET_ACCOUNT_TYPES:
        total = await ManualAssetRepository(db).sum_valuation_by_account(account.id)
        sums = await tx_repo.sum_for_account(account.id)
        balance = total + sums["transfer_in"] - sums["transfer_out"]
        return BalanceSummary(balance=balance)

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
    cost = sum((i.quantity * i.avg_price for i in items), Decimal("0.00"))
    valuation = sum((i.quantity * i.current_price for i in items), Decimal("0.00"))
    profit_loss = valuation - cost
    profit_loss_rate = (profit_loss / cost * Decimal("100")) if cost > 0 else Decimal("0.00")
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
        is_manual_asset=account.account_type in MANUAL_ASSET_ACCOUNT_TYPES,
        cash=summary.cash,
        portfolio_cost=summary.portfolio_cost,
        portfolio_valuation=summary.portfolio_valuation,
        portfolio_profit_loss=summary.portfolio_profit_loss,
        portfolio_profit_loss_rate=summary.portfolio_profit_loss_rate,
    )


async def list_accounts(
    db: AsyncSession,
    household: Household,
    *,
    search_term: str | None = None,
    account_type: str | None = None,
    is_archived: bool | None = None,
) -> list[AccountResponse]:
    """내부용 — sort_order 정렬 유지 (portfolio overview / snapshot 에서 호출)."""
    repo = AccountRepository(db)
    tx_repo = TransactionRepository(db)
    accounts = await repo.search_by_household_id(
        household.id,
        search_term=search_term,
        account_type=account_type,
        is_archived=is_archived,
    )
    responses = []
    for a in accounts:
        summary = await _calc_balance(tx_repo, a, db)
        responses.append(_build_response(a, summary))
    return responses


async def list_accounts_cursor(
    db: AsyncSession,
    household: Household,
    *,
    search_term: str | None = None,
    account_type: str | None = None,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 30,
) -> "CursorPage[AccountResponse]":
    """관리 페이지용 — frst_reg_dt DESC 정렬, cursor 무한 스크롤."""
    repo = AccountRepository(db)
    tx_repo = TransactionRepository(db)
    rows = await repo.list_by_cursor(
        household.id,
        search_term=search_term,
        account_type=account_type,
        is_archived=is_archived,
        cursor=cursor,
        limit=limit,
    )
    has_next = len(rows) > limit
    rows = rows[:limit]

    items: list[AccountResponse] = []
    for a in rows:
        summary = await _calc_balance(tx_repo, a, db)
        items.append(_build_response(a, summary))

    total_count = await repo.count_search(
        household.id,
        search_term=search_term,
        account_type=account_type,
        is_archived=is_archived,
    )

    next_cursor: str | None = None
    if has_next and rows:
        last = rows[-1]
        next_cursor = f"{last.frst_reg_dt.isoformat()}|{last.id}"

    return CursorPage(
        items=items,
        next_cursor=next_cursor,
        has_next=has_next,
        total_count=total_count,
    )


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
        zero = Decimal("0.00")
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

    # 자식 존재 가드 — 거래(출금/입금 양방향) 또는 종목이 연결돼 있으면 삭제 차단.
    # 이체는 양쪽 통장을 참조하므로 cascade 대신 차단이 안전(상대 통장 잔액 보호).
    if await TransactionRepository(db).exists_active_by_account_id(account_id):
        raise CustomException(ErrorCode.ACCOUNT_HAS_DEPENDENTS)
    if await PortfolioItemRepository(db).count_active_by_account_id(account_id) > 0:
        raise CustomException(ErrorCode.ACCOUNT_HAS_DEPENDENTS)

    account.data_stat_cd = DataStatus.DELETED
    await db.flush()
    logger.info("통장 삭제 (account_id=%s)", account_id)


async def get_account_detail(
    db: AsyncSession, household: Household, account_id: UUID,
) -> AccountResponse:
    """통장 단건 조회 — 잔액 + PNL 포함"""
    repo = AccountRepository(db)
    account = await repo.find_by_id(account_id)
    if not account or account.household_id != household.id or account.data_stat_cd != DataStatus.ACTIVE:
        raise CustomException(ErrorCode.NOT_FOUND)
    tx_repo = TransactionRepository(db)
    summary = await _calc_balance(tx_repo, account, db)
    return _build_response(account, summary)


def _today_kst() -> date:
    """KST 기준 오늘 — 리포트 이번달 판정용."""
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def _shift_months(d: date, delta: int) -> date:
    """d 기준 delta 개월 이동한 달의 1일."""
    total = d.year * 12 + (d.month - 1) + delta
    return date(total // 12, total % 12 + 1, 1)


async def get_account_report(
    db: AsyncSession,
    household: Household,
    account_id: UUID,
    from_date: date | None = None,
    to_date: date | None = None,
) -> AccountReportResponse:
    """계좌별 리포트 — 현재 잔액 + 월별 수입/지출 추이.

    박제된 과거 월 + 아직 박제 전인 이번달(실시간 집계)을 합쳐 내려준다.
    기본 기간은 최근 12개월(이번달 포함).
    """
    repo = AccountRepository(db)
    account = await repo.find_by_id(account_id)
    if not account or account.household_id != household.id or account.data_stat_cd != DataStatus.ACTIVE:
        raise CustomException(ErrorCode.NOT_FOUND)

    today = _today_kst()
    this_month_first = today.replace(day=1)
    if not to_date:
        to_date = this_month_first
    if not from_date:
        from_date = _shift_months(to_date, -11)

    snap_repo = AccountSnapshotRepository(db)
    snaps = await snap_repo.find_by_account_and_range(account_id, from_date, to_date)

    flows = [
        AccountMonthlyFlow(
            month_date=s.snapshot_date,
            income=s.monthly_income,
            expense=s.monthly_expense,
            fixed_expense=s.monthly_fixed_expense,
            balance=s.balance,
        )
        for s in snaps
    ]

    tx_repo = TransactionRepository(db)
    summary = await _calc_balance(tx_repo, account, db)

    # 이번달은 아직 박제 전 — 스냅샷에 없으면 실시간 집계로 보강 (잔액은 현재값)
    if to_date >= this_month_first and not any(
        s.snapshot_date == this_month_first for s in snaps
    ):
        m = await tx_repo.sum_by_account_for_month(account_id, today.year, today.month)
        flows.append(
            AccountMonthlyFlow(
                month_date=this_month_first,
                income=m["income"],
                expense=m["expense"],
                fixed_expense=m["fixed_expense"],
                balance=summary.balance,
            )
        )

    return AccountReportResponse(
        account_id=account.id,
        account_name=account.name,
        account_type=account.account_type,
        balance=summary.balance,
        monthly_flows=flows,
    )
