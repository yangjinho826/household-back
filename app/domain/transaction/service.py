import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
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
    CalendarDay,
    CalendarResponse,
    TransactionCreateRequest,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdateRequest,
)
from app.domain.user.model import User

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
        next_cursor = f"{last.tx_date.isoformat()}|{last.id}"

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
        is_fixed=tx.is_fixed,
        memo=tx.memo,
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
        is_fixed=req.is_fixed,
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
    if req.is_fixed is not None:
        tx.is_fixed = req.is_fixed
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
        elif tx_type == TxType.EXPENSE:
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
