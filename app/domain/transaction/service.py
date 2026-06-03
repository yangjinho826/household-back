import logging
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.domain.account.enum import AccountType
from app.domain.account.repository import AccountRepository
from app.domain.category.repository import CategoryRepository
from app.domain.household.model import Household
from app.domain.transaction.enum import TxType
from app.domain.transaction.model import Transaction
from app.domain.transaction.repository import (
    TransactionFilter,
    TransactionRepository,
)
from app.domain.transaction.schema import (
    AccountLedgerItem,
    AccountLedgerPage,
    CalendarDay,
    CalendarFullResponse,
    CalendarResponse,
    TransactionCreateRequest,
    TransactionFormOptionsResponse,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdateRequest,
)
from app.domain.user.model import User

# running balance 를 지원하는 거래계좌 — 현금흐름 잔액이 곧 balance.
# INVESTMENT(평가액 섞임)·REAL_ESTATE/PENSION/COMMODITY(거래 없음)는 제외.
_LEDGER_ACCOUNT_TYPES = (AccountType.LIVING, AccountType.SAVINGS, AccountType.OTHER)

logger = logging.getLogger(__name__)


async def _validate_fk_belong_to_household(
    db: AsyncSession,
    household_id: UUID,
    account_ids: list[UUID],
    category_ids: list[UUID],
) -> None:
    """account/category 가 모두 같은 household 소속인지 검증"""
    if account_ids:
        accounts = await AccountRepository(db).find_by_ids(account_ids)
        if len(accounts) != len(set(account_ids)):
            raise CustomException(ErrorCode.NOT_FOUND)
        for a in accounts:
            if a.household_id != household_id or a.data_stat_cd != DataStatus.ACTIVE:
                raise CustomException(ErrorCode.NOT_FOUND)
    if category_ids:
        categories = await CategoryRepository(db).find_by_ids(category_ids)
        if len(categories) != len(set(category_ids)):
            raise CustomException(ErrorCode.NOT_FOUND)
        for c in categories:
            if c.household_id != household_id or c.data_stat_cd != DataStatus.ACTIVE:
                raise CustomException(ErrorCode.NOT_FOUND)


async def list_transactions(
    db: AsyncSession,
    household: Household,
    f: TransactionFilter,
    cursor: str | None,
    limit: int,
) -> TransactionListResponse:
    repo = TransactionRepository(db)
    rows = await repo.list_by_cursor(household.id, f, cursor, limit)
    total = await repo.count(household.id, f)

    has_next = len(rows) > limit
    items_rows = rows[:limit]

    # account/category 일괄 조회
    account_ids = {r.account_id for r in items_rows}
    account_ids.update({r.to_account_id for r in items_rows if r.to_account_id})
    category_ids = {r.category_id for r in items_rows if r.category_id}

    accounts = await AccountRepository(db).find_by_ids(list(account_ids))
    categories = await CategoryRepository(db).find_by_ids(list(category_ids))
    account_map = {a.id: a for a in accounts}
    category_map = {c.id: c for c in categories}

    items = [_build_response(r, account_map, category_map) for r in items_rows]

    next_cursor = None
    if has_next:
        last = items_rows[-1]
        next_cursor = (
            f"{last.tx_date.isoformat()}|{last.frst_reg_dt.isoformat()}|{last.id}"
        )

    return TransactionListResponse(
        items=items,
        next_cursor=next_cursor,
        has_next=has_next,
        total_count=total,
    )


def _build_response(
    tx: Transaction,
    account_map: dict,
    category_map: dict,
) -> TransactionResponse:
    account = account_map.get(tx.account_id)
    to_account = account_map.get(tx.to_account_id) if tx.to_account_id else None
    category = category_map.get(tx.category_id) if tx.category_id else None
    return TransactionResponse(
        id=tx.id,
        household_id=tx.household_id,
        tx_type=tx.tx_type,
        amount=tx.amount,
        tx_date=tx.tx_date,
        account_id=tx.account_id,
        account_name=account.name if account else None,
        to_account_id=tx.to_account_id,
        to_account_name=to_account.name if to_account else None,
        category_id=tx.category_id,
        category_name=category.name if category else None,
        category_color=category.color if category else None,
        category_icon=category.icon if category else None,
        paid_by_user_id=tx.paid_by_user_id,
        fixed_expense_id=tx.fixed_expense_id,
        memo=tx.memo,
    )


def _signed_amount(tx: Transaction, account_id: UUID) -> Decimal:
    """이 계좌 관점의 부호 금액. 이체는 출금계좌 −, 입금계좌 +."""
    if tx.tx_type == TxType.TRANSFER and tx.to_account_id == account_id:
        return tx.amount  # 이체 입금
    if tx.tx_type == TxType.INCOME:
        return tx.amount
    return -tx.amount  # EXPENSE/FIXED_EXPENSE/이체 출금


def _split_ledger_cursor(cursor: str | None) -> tuple[str | None, Decimal | None]:
    """ledger 커서 = "{tx_date}|{frst_reg_dt}|{id}|{carry_balance}".

    carry_balance 는 다음 페이지 첫 행의 시작 잔액(이전 페이지 끝에서 이어받음).
    list_by_cursor 가 쓰는 정렬 커서는 앞 3-tuple 뿐이라 carry 를 떼어 분리한다.
    """
    if not cursor:
        return None, None
    base, _, carry_str = cursor.rpartition("|")
    if not base:
        return cursor, None
    try:
        return base, Decimal(carry_str)
    except (InvalidOperation, ValueError):
        return cursor, None


async def list_account_ledger(
    db: AsyncSession,
    household: Household,
    account_id: UUID,
    cursor: str | None,
    limit: int,
    year: int | None = None,
    month: int | None = None,
) -> AccountLedgerPage:
    """계좌별 거래 이력 — 각 행에 running balance(거래 후 잔액).

    잔액은 "기준 잔액에서 desc 로 역산". 첫 페이지 첫 행의 잔액 = 그 시점까지의
    누적 현금흐름 잔액, 한 칸 옛 거래로 내려갈 때마다 위 행의 signed_amount 를
    빼서 그 아래 잔액을 만든다. 페이지 경계는 carry 를 커서에 실어 이어붙인다.

    year+month 를 주면 그 달 거래만(거래 탭). 기준점은 "그 달 말까지의 누적 잔액"
    이라 미래 달 거래와 무관하게 그 달 안에서 잔액이 맞는다. 없으면 전체(계좌 상세).
    """
    repo = TransactionRepository(db)
    account = await AccountRepository(db).find_by_id(account_id)
    if account is None or account.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)
    if account.account_type not in _LEDGER_ACCOUNT_TYPES:
        raise CustomException(ErrorCode.BAD_REQUEST)

    tx_cursor, carry = _split_ledger_cursor(cursor)
    if year is not None and month is not None:
        f = TransactionFilter(account_id=account_id, year=year, month=month)
        balance_to_date: date | None = date(year, month, monthrange(year, month)[1])
    else:
        f = TransactionFilter(account_id=account_id)
        balance_to_date = None
    rows = await repo.list_by_cursor(household.id, f, tx_cursor, limit)
    total = await repo.count(household.id, f)

    has_next = len(rows) > limit
    items_rows = rows[:limit]

    # 시작 잔액 — 첫 페이지면 기준 시점까지의 누적 현금흐름 잔액, 이어지는 페이지면 carry.
    if carry is not None:
        running = carry
    else:
        sums = await repo.sum_for_account(account_id, to_date=balance_to_date)
        running = (
            account.start_balance
            + sums["income"]
            - sums["expense"]
            - sums["transfer_out"]
            + sums["transfer_in"]
        )

    account_ids = {r.account_id for r in items_rows}
    account_ids.update({r.to_account_id for r in items_rows if r.to_account_id})
    category_ids = {r.category_id for r in items_rows if r.category_id}
    accounts = await AccountRepository(db).find_by_ids(list(account_ids))
    categories = await CategoryRepository(db).find_by_ids(list(category_ids))
    account_map = {a.id: a for a in accounts}
    category_map = {c.id: c for c in categories}

    items: list[AccountLedgerItem] = []
    for r in items_rows:
        signed = _signed_amount(r, account_id)
        base = _build_response(r, account_map, category_map)
        items.append(
            AccountLedgerItem(
                **base.model_dump(),
                signed_amount=signed,
                balance_after=running,
            )
        )
        running -= signed  # 한 칸 옛 거래의 잔액

    next_cursor = None
    if has_next:
        last = items_rows[-1]
        next_cursor = (
            f"{last.tx_date.isoformat()}|{last.frst_reg_dt.isoformat()}"
            f"|{last.id}|{running}"
        )

    return AccountLedgerPage(
        items=items,
        next_cursor=next_cursor,
        has_next=has_next,
        total_count=total,
    )


async def create_transaction(
    db: AsyncSession,
    household: Household,
    req: TransactionCreateRequest,
    current_user: User,
) -> TransactionResponse:
    account_ids = [req.account_id]
    if req.to_account_id is not None:
        account_ids.append(req.to_account_id)
    category_ids = [req.category_id] if req.category_id else []
    await _validate_fk_belong_to_household(db, household.id, account_ids, category_ids)

    tx = Transaction(
        household_id=household.id,
        tx_type=req.tx_type,
        amount=req.amount,
        tx_date=req.tx_date,
        account_id=req.account_id,
        to_account_id=req.to_account_id,
        category_id=req.category_id,
        paid_by_user_id=req.paid_by_user_id or current_user.id,
        fixed_expense_id=req.fixed_expense_id,
        memo=req.memo,
        data_stat_cd=DataStatus.ACTIVE,
    )
    await TransactionRepository(db).save(tx)
    logger.info("거래 생성 (tx_id=%s, type=%s, amount=%s)", tx.id, req.tx_type, req.amount)
    return await _single_response(db, tx)


async def update_transaction(
    db: AsyncSession,
    household: Household,
    tx_id: UUID,
    req: TransactionUpdateRequest,
) -> TransactionResponse:
    repo = TransactionRepository(db)
    tx = await repo.find_by_id(tx_id)
    if not tx or tx.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    new_account_id = req.account_id if req.account_id is not None else tx.account_id
    new_to_account_id = req.to_account_id if req.to_account_id is not None else tx.to_account_id
    new_category_id = req.category_id if req.category_id is not None else tx.category_id

    fk_accounts = [new_account_id]
    if new_to_account_id is not None:
        fk_accounts.append(new_to_account_id)
    fk_categories = [new_category_id] if new_category_id else []
    await _validate_fk_belong_to_household(db, household.id, fk_accounts, fk_categories)

    if req.tx_type is not None:
        tx.tx_type = req.tx_type
    if req.amount is not None:
        tx.amount = req.amount
    if req.tx_date is not None:
        tx.tx_date = req.tx_date
    if req.account_id is not None:
        tx.account_id = req.account_id
    if req.to_account_id is not None:
        tx.to_account_id = req.to_account_id
    if req.category_id is not None:
        tx.category_id = req.category_id
    if req.paid_by_user_id is not None:
        tx.paid_by_user_id = req.paid_by_user_id
    if req.fixed_expense_id is not None:
        tx.fixed_expense_id = req.fixed_expense_id
    if req.memo is not None:
        tx.memo = req.memo

    # type 별 일관성 재검증
    if tx.tx_type == TxType.TRANSFER:
        if tx.to_account_id is None or tx.to_account_id == tx.account_id:
            raise CustomException(ErrorCode.BAD_REQUEST)

    await db.flush()
    return await _single_response(db, tx)


async def delete_transaction(
    db: AsyncSession, household: Household, tx_id: UUID,
) -> None:
    repo = TransactionRepository(db)
    tx = await repo.find_by_id(tx_id)
    if not tx or tx.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    tx.data_stat_cd = DataStatus.DELETED
    await db.flush()
    logger.info("거래 삭제 (tx_id=%s)", tx_id)


async def get_transaction_detail(
    db: AsyncSession, household: Household, tx_id: UUID,
) -> TransactionResponse:
    """거래 단건 조회 — account/category 조인 필드 포함"""
    repo = TransactionRepository(db)
    tx = await repo.find_by_id(tx_id)
    if not tx or tx.household_id != household.id or tx.data_stat_cd != DataStatus.ACTIVE:
        raise CustomException(ErrorCode.NOT_FOUND)
    return await _single_response(db, tx)


async def _single_response(db: AsyncSession, tx: Transaction) -> TransactionResponse:
    """단일 거래 응답 — account/category JOIN"""
    account_ids = [tx.account_id]
    if tx.to_account_id:
        account_ids.append(tx.to_account_id)
    category_ids = [tx.category_id] if tx.category_id else []

    accounts = await AccountRepository(db).find_by_ids(account_ids)
    categories = await CategoryRepository(db).find_by_ids(category_ids)
    return _build_response(
        tx,
        {a.id: a for a in accounts},
        {c.id: c for c in categories},
    )


async def get_calendar_full(
    db: AsyncSession, household: Household, year: int, month: int,
) -> CalendarFullResponse:
    """달력 페이지 1호출 — calendar(일별 합계) + stats(카테고리별) + 그달 거래 전부."""
    # 순환 import 방지 — 함수 안에서 import
    from app.domain.stats import service as stats_service

    calendar = await get_calendar(db, household, year, month)
    stats = await stats_service.get_monthly_stats(db, household, year, month)

    f = TransactionFilter(year=year, month=month)
    # 한 달치 거래 — 가계부 평균 100 미만이라 cursor 페이징 불필요, 큰 limit 로 통째.
    tx_page = await list_transactions(db, household, f, cursor=None, limit=500)

    return CalendarFullResponse(
        year=calendar.year,
        month=calendar.month,
        monthly_income=calendar.monthly_income,
        monthly_expense=calendar.monthly_expense,
        monthly_transfer=calendar.monthly_transfer,
        days=calendar.days,
        by_category=stats.by_category,
        transactions=tx_page.items,
    )


async def get_form_options(
    db: AsyncSession, household: Household,
) -> TransactionFormOptionsResponse:
    """거래 등록/수정 폼 옵션 — 통장 + 카테고리 + 활성 고정지출 한 번에."""
    # 순환 import 방지
    from app.domain.account import service as account_service
    from app.domain.category import service as category_service
    from app.domain.fixed import service as fixed_service

    accounts = await account_service.list_accounts(db, household)
    categories = await category_service.list_categories(db, household)
    fixed_expenses = await fixed_service.list_fixed_expenses(
        db, household, is_archived=False,
    )

    return TransactionFormOptionsResponse(
        accounts=accounts,
        categories=categories,
        fixed_expenses=fixed_expenses,
    )


async def get_calendar(
    db: AsyncSession, household: Household, year: int, month: int,
) -> CalendarResponse:
    """달력 뷰 — 일별 income/expense/transfer 합계 + 월간 합계"""
    repo = TransactionRepository(db)
    rows = await repo.daily_sums_for_month(household.id, year, month)

    by_date: dict[date, dict] = {}
    monthly_income = Decimal("0.00")
    monthly_expense = Decimal("0.00")
    monthly_transfer = Decimal("0.00")

    for tx_date, tx_type, total, cnt in rows:
        d = by_date.setdefault(
            tx_date,
            {
                "income": Decimal("0.00"),
                "expense": Decimal("0.00"),
                "transfer": Decimal("0.00"),
                "count": 0,
            },
        )
        if tx_type == TxType.INCOME:
            d["income"] += total
            monthly_income += total
        elif tx_type in (TxType.EXPENSE, TxType.FIXED_EXPENSE):
            d["expense"] += total
            monthly_expense += total
        elif tx_type == TxType.TRANSFER:
            d["transfer"] += total
            monthly_transfer += total
        d["count"] += cnt

    days = [
        CalendarDay(
            date=d,
            income=v["income"],
            expense=v["expense"],
            transfer=v["transfer"],
            count=v["count"],
        )
        for d, v in sorted(by_date.items())
    ]

    return CalendarResponse(
        year=year,
        month=month,
        monthly_income=monthly_income,
        monthly_expense=monthly_expense,
        monthly_transfer=monthly_transfer,
        days=days,
    )
