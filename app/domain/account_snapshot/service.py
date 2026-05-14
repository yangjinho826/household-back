import logging
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.domain.account.model import Account
from app.domain.account.repository import AccountRepository
from app.domain.account.service import _calc_balance
from app.domain.account_snapshot.model import AccountSnapshot
from app.domain.account_snapshot.repository import AccountSnapshotRepository
from app.domain.account_snapshot.schema import (
    SnapshotMonth,
    SnapshotMonthBalance,
    SnapshotYearlyResponse,
)
from app.domain.household.model import Household
from app.domain.portfolio.snapshot_service import snapshot_household_portfolio
from app.domain.transaction.repository import TransactionRepository

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


def _today_kst() -> date:
    """한국 시각 기준 오늘 — 운영 서버 UTC 여도 KST 자정 경계 보장"""
    return datetime.now(KST).date()


def _normalize_to_month_first(d: date) -> date:
    return d.replace(day=1)


def _shift_months(d: date, delta_months: int) -> date:
    """delta_months 만큼 이동한 그 달 1일"""
    total = d.year * 12 + (d.month - 1) + delta_months
    y, m = divmod(total, 12)
    return date(y, m + 1, 1)


def _build_month(
    snapshot_date: date,
    snapshots: list[AccountSnapshot],
    account_map: dict,
) -> SnapshotMonth:
    items = []
    total_balance = Decimal("0.00")
    total_income = Decimal("0.00")
    total_expense = Decimal("0.00")
    total_fixed_expense = Decimal("0.00")
    for s in snapshots:
        a = account_map.get(s.account_id)
        items.append(
            SnapshotMonthBalance(
                account_id=s.account_id,
                account_name=a.name if a else "(삭제됨)",
                balance=s.balance,
                monthly_income=s.monthly_income,
                monthly_expense=s.monthly_expense,
                monthly_fixed_expense=s.monthly_fixed_expense,
            )
        )
        total_balance += s.balance
        total_income += s.monthly_income
        total_expense += s.monthly_expense
        total_fixed_expense += s.monthly_fixed_expense
    return SnapshotMonth(
        snapshot_date=snapshot_date,
        total_balance=total_balance,
        total_income=total_income,
        total_expense=total_expense,
        total_fixed_expense=total_fixed_expense,
        accounts=items,
    )


async def create_target_month_snapshot(
    db: AsyncSession, household: Household,
) -> SnapshotMonth:
    """지난달 마감 박제 — 예: 6/1 ~ 6/말 사이 호출하면 5월을 박제.
    1월에 호출하면 작년 12월 박제.
    """
    repo = AccountSnapshotRepository(db)
    # 지난달 1일 = 이번달 1일 - 1개월. _shift_months 가 연도 넘김 처리.
    target_date = _shift_months(_normalize_to_month_first(_today_kst()), -1)

    if await repo.has_active_for_month(household.id, target_date):
        raise CustomException(ErrorCode.SNAPSHOT_ALREADY_EXISTS)

    accounts = [
        a for a in await AccountRepository(db).find_active_by_household_id(household.id)
        if not a.is_archived
    ]

    tx_repo = TransactionRepository(db)
    # 모든 account 의 월 합산을 한 번에 가져와 dict 룩업 — N+1 회피
    monthly_sums = await tx_repo.sum_monthly_for_household(
        household.id, target_date.year, target_date.month,
    )
    _empty_monthly = {
        "income": Decimal("0"),
        "expense": Decimal("0"),
        "fixed_expense": Decimal("0"),
    }
    snapshots: list[AccountSnapshot] = []
    for a in accounts:
        summary = await _calc_balance(tx_repo, a, db)
        monthly = monthly_sums.get(a.id, _empty_monthly)
        snapshots.append(
            AccountSnapshot(
                account_id=a.id,
                snapshot_date=target_date,
                balance=summary.balance,
                monthly_income=monthly["income"],
                monthly_expense=monthly["expense"],
                monthly_fixed_expense=monthly["fixed_expense"],
                data_stat_cd=DataStatus.ACTIVE,
            )
        )

    await repo.save_all(snapshots)

    # 종목 박제 — portfolio 도메인이 자기 책임
    await snapshot_household_portfolio(db, household, target_date)

    logger.info(
        "자산 스냅샷 저장 (household_id=%s, date=%s, accounts=%d)",
        household.id, target_date, len(snapshots),
    )

    account_map = {a.id: a for a in accounts}
    return _build_month(target_date, snapshots, account_map)


async def get_yearly_snapshots(
    db: AsyncSession,
    household: Household,
    from_date: date | None = None,
    to_date: date | None = None,
) -> SnapshotYearlyResponse:
    repo = AccountSnapshotRepository(db)
    today = _today_kst()
    # 박제 가능한 월 = 지난달. 이번달 1일에서 -1.
    target_month = _shift_months(_normalize_to_month_first(today), -1)

    if not to_date:
        to_date = target_month
    else:
        to_date = _normalize_to_month_first(to_date)
    if not from_date:
        from_date = _shift_months(to_date, -11)
    else:
        from_date = _normalize_to_month_first(from_date)

    rows = await repo.find_by_household_and_range(household.id, from_date, to_date)

    account_ids = list({s.account_id for s in rows})
    accounts: list[Account] = await AccountRepository(db).find_by_ids(account_ids)
    account_map = {a.id: a for a in accounts}

    months_grouped: dict[date, list[AccountSnapshot]] = {}
    for s in rows:
        months_grouped.setdefault(s.snapshot_date, []).append(s)

    months = [
        _build_month(d, snaps, account_map)
        for d, snaps in sorted(months_grouped.items(), key=lambda kv: kv[0])
    ]

    saved = await repo.has_active_for_month(household.id, target_month)

    return SnapshotYearlyResponse(
        months=months,
        target_month_saved=saved,
        target_month_date=target_month,
    )
