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
from app.domain.household.repository import HouseholdRepository
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


def _target_month() -> date:
    """박제 대상 월 = 지난달 1일. _shift_months 가 연도 넘김 처리."""
    return _shift_months(_normalize_to_month_first(_today_kst()), -1)


async def _build_and_save_snapshot(
    db: AsyncSession, household: Household, target_date: date,
) -> SnapshotMonth:
    """실제 박제 실행 — 중복 체크 없음 (호출자가 책임).

    계좌별 잔액 + 그달 수입/지출/고정지출 박제 + 종목 평가액 박제.
    """
    accounts = [
        a for a in await AccountRepository(db).find_active_by_household_id(household.id)
        if not a.is_archived
    ]
    if not accounts:
        # 계좌 없는 가계부 — 박제할 게 없음. 빈 월 반환.
        return _build_month(target_date, [], {})

    tx_repo = TransactionRepository(db)
    snapshots: list[AccountSnapshot] = []
    for a in accounts:
        summary = await _calc_balance(tx_repo, a, db)
        monthly = await tx_repo.sum_by_account_for_month(
            a.id, target_date.year, target_date.month,
        )
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

    await AccountSnapshotRepository(db).save_all(snapshots)

    # 종목 박제 — portfolio 도메인이 자기 책임
    await snapshot_household_portfolio(db, household, target_date)

    account_map = {a.id: a for a in accounts}
    return _build_month(target_date, snapshots, account_map)


async def create_target_month_snapshot(
    db: AsyncSession, household: Household,
) -> SnapshotMonth:
    """수동 박제 — 6/1 ~ 6/말 사이 호출하면 5월 박제. 이미 있으면 raise."""
    repo = AccountSnapshotRepository(db)
    target_date = _target_month()

    if await repo.has_active_for_month(household.id, target_date):
        raise CustomException(ErrorCode.SNAPSHOT_ALREADY_EXISTS)

    result = await _build_and_save_snapshot(db, household, target_date)
    logger.info("자산 스냅샷 저장 (household_id=%s, date=%s)", household.id, target_date)
    return result


async def create_monthly_snapshots_for_all(db: AsyncSession) -> int:
    """매월 자동 박제 — 모든 활성 가계부의 지난달 박제. 이미 있으면 skip.

    스케줄러(매월 1일)에서 호출. 반환값은 신규 박제된 가계부 수.
    """
    target_date = _target_month()
    repo = AccountSnapshotRepository(db)
    households = await HouseholdRepository(db).find_all_active()

    created = 0
    for h in households:
        if await repo.has_active_for_month(h.id, target_date):
            continue
        result = await _build_and_save_snapshot(db, h, target_date)
        if result.accounts:  # 계좌 없는 빈 가계부는 카운트 제외
            created += 1

    logger.info(
        "월간 자동 박제 완료 (households=%d, created=%d, date=%s)",
        len(households), created, target_date,
    )
    return created


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
