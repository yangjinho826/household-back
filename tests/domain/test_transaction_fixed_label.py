"""고정지출 거래의 화면 라벨 — `TransactionResponse.fixed_expense_name` (TDD/RED 선행).

**공개 계약** — 거래 응답은 `fixed_expense_id` 가 있으면 그 고정지출의 이름을 함께 준다.
없으면 `None`. 화면에서 "고정지출 · 월세" 처럼 어떤 고정지출인지 보여주기 위한 필드다.

| # | 시나리오 |
|---|---|
| 1 | 고정지출에 매핑된 거래는 목록에서 이름이 채워진다 |
| 2 | 일반 지출은 이름이 None |
| 3 | 보관(archived)된 고정지출에 물린 과거 거래도 이름이 채워진다 |
| 4 | 삭제(soft)된 고정지출에 물린 과거 거래도 이름이 채워진다 |
| 5 | 서로 다른 고정지출에 물린 거래들이 각각 올바른 이름을 받는다 |
| 6 | 상세 조회에서도 채워진다 |
| 7 | 계좌 원장에서도 채워진다 |
| 8 | 달력 1호출에서도 채워진다 |
| 9 | 다른 가계부의 고정지출 이름이 섞이지 않는다 |
| 10 | 거래가 N건이어도 fixed_expenses 조회는 1회 (N+1 없음) |

3·4 가 이 설계의 핵심 — 보관/삭제는 "앞으로 안 씀"이지 "과거 기록을 지움"이 아니다.
활성 목록(`list_fixed_expenses(is_archived=False)`)만으로 이름을 붙이면 과거 거래가
이름 없이 깨지므로, 이름 조회는 상태 필터 없이 id 로만 해야 한다.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event

from app.core.database import engine
from app.domain.fixed import service as fixed_service
from app.domain.fixed.model import FixedExpense
from app.domain.transaction import service
from app.domain.transaction.enum import TxType
from app.domain.transaction.repository import TransactionFilter
from app.domain.transaction.schema import TransactionCreateRequest
from tests.fixtures.factory import (
    LedgerContext,
    fixed_expense_factory,
    seed_ledger_context,
    user_factory,
)

TX_DATE = date(2026, 3, 25)


@pytest_asyncio.fixture
async def ctx(db) -> LedgerContext:
    return await seed_ledger_context(db)


async def _create_fixed_tx(db, ctx: LedgerContext, fixed: FixedExpense, *, amount: str = "500000"):
    """고정지출에 매핑된 FIXED_EXPENSE 거래 1건."""
    return await service.create_transaction(
        db,
        ctx.household,
        TransactionCreateRequest(
            txType=TxType.FIXED_EXPENSE,
            amount=Decimal(amount),
            txDate=TX_DATE,
            accountId=ctx.account.id,
            fixedExpenseId=fixed.id,
        ),
        ctx.user,
    )


async def _create_plain_expense(db, ctx: LedgerContext):
    """고정지출과 무관한 일반 지출 1건."""
    return await service.create_transaction(
        db,
        ctx.household,
        TransactionCreateRequest(
            txType=TxType.EXPENSE,
            amount=Decimal("12000"),
            txDate=TX_DATE,
            accountId=ctx.account.id,
            categoryId=ctx.expense_category.id,
        ),
        ctx.user,
    )


async def _list_items(db, ctx: LedgerContext, **filter_kwargs):
    page = await service.list_transactions(
        db, ctx.household, TransactionFilter(**filter_kwargs), cursor=None, limit=100,
    )
    return page.items


async def test_고정지출_거래는_목록에_고정지출명이_채워진다(db, ctx):
    # given
    fixed = await fixed_expense_factory(db, household=ctx.household, name="월세")
    await _create_fixed_tx(db, ctx, fixed)

    # when
    items = await _list_items(db, ctx, tx_type=TxType.FIXED_EXPENSE)

    # then
    assert len(items) == 1
    assert items[0].fixed_expense_id == fixed.id
    assert items[0].fixed_expense_name == "월세"


async def test_일반_지출은_고정지출명이_없다(db, ctx):
    # given
    await _create_plain_expense(db, ctx)

    # when
    items = await _list_items(db, ctx, tx_type=TxType.EXPENSE)

    # then
    assert items[0].fixed_expense_id is None
    assert items[0].fixed_expense_name is None


async def test_보관된_고정지출도_과거_거래에_이름이_남는다(db, ctx):
    """보관은 '앞으로 안 씀' — 이미 기록된 거래의 이름까지 지우면 안 된다."""
    # given
    fixed = await fixed_expense_factory(db, household=ctx.household, name="넷플릭스")
    await _create_fixed_tx(db, ctx, fixed)
    fixed.is_archived = True
    await db.flush()

    # when
    items = await _list_items(db, ctx, tx_type=TxType.FIXED_EXPENSE)

    # then
    assert items[0].fixed_expense_name == "넷플릭스"


async def test_삭제된_고정지출도_과거_거래에_이름이_남는다(db, ctx):
    """삭제는 soft delete — 거래의 fixed_expense_id 는 그대로 남는다."""
    # given
    fixed = await fixed_expense_factory(db, household=ctx.household, name="통신비")
    await _create_fixed_tx(db, ctx, fixed)
    await fixed_service.delete_fixed_expense(db, ctx.household, fixed.id)

    # when
    items = await _list_items(db, ctx, tx_type=TxType.FIXED_EXPENSE)

    # then
    assert items[0].fixed_expense_name == "통신비"


async def test_고정지출이_여러개면_각_거래가_제_이름을_받는다(db, ctx):
    # given
    rent = await fixed_expense_factory(db, household=ctx.household, name="월세")
    phone = await fixed_expense_factory(db, household=ctx.household, name="통신비")
    await _create_fixed_tx(db, ctx, rent, amount="500000")
    await _create_fixed_tx(db, ctx, phone, amount="55000")

    # when
    items = await _list_items(db, ctx, tx_type=TxType.FIXED_EXPENSE)

    # then
    by_amount = {item.amount: item.fixed_expense_name for item in items}
    assert by_amount[Decimal("500000.00")] == "월세"
    assert by_amount[Decimal("55000.00")] == "통신비"


async def test_상세_조회에도_고정지출명이_채워진다(db, ctx):
    # given
    fixed = await fixed_expense_factory(db, household=ctx.household, name="관리비")
    created = await _create_fixed_tx(db, ctx, fixed)

    # when
    detail = await service.get_transaction_detail(db, ctx.household, created.id)

    # then
    assert detail.fixed_expense_name == "관리비"


async def test_계좌_원장에도_고정지출명이_채워진다(db, ctx):
    # given
    fixed = await fixed_expense_factory(db, household=ctx.household, name="보험료")
    await _create_fixed_tx(db, ctx, fixed)

    # when
    page = await service.list_account_ledger(
        db, ctx.household, ctx.account.id, cursor=None, limit=100,
    )

    # then
    assert page.items[0].fixed_expense_name == "보험료"


async def test_달력_조회에도_고정지출명이_채워진다(db, ctx):
    # given
    fixed = await fixed_expense_factory(db, household=ctx.household, name="구독료")
    await _create_fixed_tx(db, ctx, fixed)

    # when
    calendar = await service.get_calendar_full(
        db, ctx.household, TX_DATE.year, TX_DATE.month,
    )

    # then
    names = [t.fixed_expense_name for t in calendar.transactions]
    assert "구독료" in names


async def test_다른_가계부의_고정지출명은_섞이지_않는다(db, ctx):
    """이름 조회는 id 기반 batch — 남의 가계부 이름이 새면 안 된다."""
    # given — 내 가계부 거래 1건
    mine = await fixed_expense_factory(db, household=ctx.household, name="내_월세")
    await _create_fixed_tx(db, ctx, mine)

    # 다른 사람의 가계부 + 같은 이름 자리를 노리는 고정지출
    other_user = await user_factory(db, email="other@test.com")
    other_ctx = await seed_ledger_context(db)
    other_fixed = await fixed_expense_factory(
        db, household=other_ctx.household, name="남의_월세",
    )
    await _create_fixed_tx(db, other_ctx, other_fixed)
    assert other_user.id != ctx.user.id

    # when
    items = await _list_items(db, ctx)

    # then
    names = {item.fixed_expense_name for item in items}
    assert names == {"내_월세"}


@pytest.mark.parametrize("tx_count", [5])
async def test_거래가_N건이어도_고정지출_조회는_1회다(db, ctx, tx_count):
    """N+1 방지 — 행마다 조회하면 목록이 커질수록 쿼리가 선형 증가한다."""
    # given
    fixed = await fixed_expense_factory(db, household=ctx.household, name="월세")
    for _ in range(tx_count):
        await _create_fixed_tx(db, ctx, fixed)

    fixed_selects = 0

    def _count(conn, cursor, statement, parameters, context, executemany):
        nonlocal fixed_selects
        if "fixed_expenses" in statement.lower():
            fixed_selects += 1

    # when
    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        items = await _list_items(db, ctx, tx_type=TxType.FIXED_EXPENSE)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)

    # then
    assert len(items) == tx_count
    assert fixed_selects == 1
