"""D1. 계좌 원장 running balance 정합 (명세 기반 사후검증).

**도출한 불변식** — `list_account_ledger` docstring 에서 독립 도출:
"잔액은 기준 잔액에서 desc 로 역산… 한 칸 옛 거래로 내려갈 때마다 위 행의
signed_amount 를 빼서 그 아래 잔액을 만든다. 페이지 경계는 carry 를 커서에 실어
이어붙인다." / "year+month 를 주면… 기준점은 그 달 말까지의 누적 잔액이라 미래 달
거래와 무관하게 그 달 안에서 잔액이 맞는다."

| # | 불변식 |
|---|---|
| INV-A | 끝까지 순회하면 마지막(가장 오래된) 행의 `balance_after - signed_amount` 가 `account.start_balance` 로 되돌아온다 |
| INV-B | `limit` 을 달리해도 행 순서·`balance_after` 가 동일하다 (커서 carry 연속성) |
| INV-C | 월 조회의 첫 행 잔액은 그 달 말일까지 누적 — 미래 달 거래에 영향받지 않는다 |
| INV-D | 한 이체는 출금 계좌에서 `-amount`, 입금 계좌에서 `+amount` |
| INV-E | VALUATION 은 INCREASE `+`, DECREASE `-` |

잔액은 **저장되지 않고 계산으로 만들어진다**(D2 의 실현손익과 같은 성격). 다만 D2 와
달리 부호 계산 두 경로(`_signed_amount` / `sum_for_account`)의 규칙이 일치하므로
GREEN 을 기대하고, 역산이 실제로 닫히는지를 실측한다.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest_asyncio

from app.domain.transaction import service
from app.domain.transaction.enum import TxType, ValuationDirection
from app.domain.transaction.schema import TransactionCreateRequest
from tests.fixtures.factory import LedgerContext, seed_ledger_context

START_BALANCE = Decimal("100000")

# 커서 순회가 계약을 어기고 안 끝나면 테스트가 매달리므로 상한을 둔다.
_MAX_PAGES = 50


@pytest_asyncio.fixture
async def ctx(db) -> LedgerContext:
    return await seed_ledger_context(db, start_balance=START_BALANCE)


async def _create(
    db,
    ctx: LedgerContext,
    *,
    tx_type: TxType,
    amount: str,
    tx_date: date,
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    to_account_id: UUID | None = None,
    valuation_direction: ValuationDirection | None = None,
):
    payload: dict = {
        "txType": tx_type,
        "amount": Decimal(amount),
        "txDate": tx_date,
        "accountId": account_id or ctx.account.id,
    }
    if category_id is not None:
        payload["categoryId"] = category_id
    if to_account_id is not None:
        payload["toAccountId"] = to_account_id
    if valuation_direction is not None:
        payload["valuationDirection"] = valuation_direction

    return await service.create_transaction(
        db, ctx.household, TransactionCreateRequest(**payload), ctx.user,
    )


async def _expense(db, ctx, amount: str, tx_date: date, **kwargs):
    return await _create(
        db, ctx, tx_type=TxType.EXPENSE, amount=amount, tx_date=tx_date,
        category_id=ctx.expense_category.id, **kwargs,
    )


async def _income(db, ctx, amount: str, tx_date: date, **kwargs):
    return await _create(
        db, ctx, tx_type=TxType.INCOME, amount=amount, tx_date=tx_date,
        category_id=ctx.income_category.id, **kwargs,
    )


async def _ledger(db, ctx, account_id=None, *, cursor=None, limit=100, year=None, month=None):
    return await service.list_account_ledger(
        db, ctx.household, account_id or ctx.account.id, cursor, limit, year, month,
    )


async def _collect_all(db, ctx, account_id=None, *, limit: int):
    """has_next 가 꺼질 때까지 커서를 따라가며 전 페이지를 모은다.

    돈 페이지 수까지 반환한다 — 페이지 경계를 실제로 넘었는지 단언하지 않으면
    한 페이지만 돌고도 "페이지 불변" 테스트가 통과해버린다.
    """
    items = []
    cursor = None
    total_count = 0
    for page_no in range(1, _MAX_PAGES + 1):
        page = await _ledger(db, ctx, account_id, cursor=cursor, limit=limit)
        items.extend(page.items)
        total_count = page.total_count
        if not page.has_next:
            return items, total_count, page_no
        cursor = page.next_cursor
    raise AssertionError(f"커서 순회가 {_MAX_PAGES} 페이지 안에 끝나지 않았다")


async def test_D1_1_전체_순회하면_잔액이_시작잔액으로_되돌아온다(db, ctx):
    """INV-A(닫힘) — 역산이 시작점으로 정확히 수렴하는가.

    잔액을 저장하지 않고 매번 역산하므로, 끝까지 내려갔을 때 통장 개설 잔액이
    나오지 않으면 중간 어딘가의 부호·기준점이 틀린 것이다.
    """
    # given: 시작잔액 100,000 + 수입·지출·이체 5건
    await _income(db, ctx, "50000", date(2026, 1, 5))
    await _expense(db, ctx, "30000", date(2026, 1, 10))
    await _create(
        db, ctx, tx_type=TxType.TRANSFER, amount="20000", tx_date=date(2026, 1, 15),
        to_account_id=ctx.other_account.id,
    )
    await _expense(db, ctx, "10000", date(2026, 1, 20))
    await _income(db, ctx, "5000", date(2026, 1, 25))

    # when
    items, total_count, _ = await _collect_all(db, ctx, limit=100)

    # then: 첫 행(최신)은 현재 잔액
    expected_now = START_BALANCE + 50000 - 30000 - 20000 - 10000 + 5000
    assert total_count == 5
    assert items[0].balance_after == expected_now

    # then: 마지막 행에서 그 거래를 되돌리면 시작 잔액
    oldest = items[-1]
    assert oldest.balance_after - oldest.signed_amount == START_BALANCE

    # then: 인접 행끼리도 한 칸씩 정확히 이어진다
    for upper, lower in zip(items, items[1:]):
        assert upper.balance_after - upper.signed_amount == lower.balance_after


async def test_D1_2_limit_이_달라도_행과_잔액이_동일하다(db, ctx):
    """INV-B(페이지 불변) — 커서 carry 로 이어붙인 결과가 통짜 조회와 같은가.

    2페이지부터는 start_balance 를 재계산하지 않고 커서에 실린 carry 를 쓰므로,
    carry 가 어긋나면 페이지 경계에서만 잔액이 튄다.
    """
    # given: 거래 6건
    for day in range(1, 7):
        await _expense(db, ctx, "1000", date(2026, 1, day))

    # when: 한 번에 vs 2건씩 3페이지
    whole, whole_total, whole_pages = await _collect_all(db, ctx, limit=100)
    paged, paged_total, paged_pages = await _collect_all(db, ctx, limit=2)

    # then: 페이지 경계를 실제로 넘었어야 이 테스트가 carry 를 검증한 것이다
    assert whole_pages == 1
    assert paged_pages == 3

    assert whole_total == paged_total == 6
    assert [(i.id, i.balance_after) for i in whole] == [
        (i.id, i.balance_after) for i in paged
    ]


async def test_D1_3_월_조회_잔액은_미래_달_거래에_영향받지_않는다(db, ctx):
    """INV-C(월 기준점) — 기준점이 '그 달 말일까지 누적'인가.

    전체 누적을 기준점으로 쓰면 미래 달 거래가 그 달 잔액을 오염시킨다.
    """
    # given: 전월 2건 + 당월 2건
    await _income(db, ctx, "10000", date(2025, 12, 10))
    await _expense(db, ctx, "4000", date(2025, 12, 20))
    await _income(db, ctx, "7000", date(2026, 1, 10))
    await _expense(db, ctx, "2000", date(2026, 1, 20))

    before = await _ledger(db, ctx, year=2026, month=1)

    # when: 다음 달 거래를 추가
    await _income(db, ctx, "999999", date(2026, 2, 5))
    await _expense(db, ctx, "888888", date(2026, 2, 15))

    after = await _ledger(db, ctx, year=2026, month=1)

    # then: 당월 첫 행 잔액 = 시작잔액 + 전월 + 당월 (2월 제외), 추가 전후 동일
    expected = START_BALANCE + 10000 - 4000 + 7000 - 2000
    assert before.items[0].balance_after == expected
    assert after.items[0].balance_after == expected
    assert before.total_count == after.total_count == 2


async def test_D1_4_이체는_출금계좌에서_음수_입금계좌에서_양수다(db, ctx):
    """INV-D(이체 부호) — 한 거래가 두 원장에 반대 부호로 나타나는가."""
    # given
    tx = await _create(
        db, ctx, tx_type=TxType.TRANSFER, amount="20000", tx_date=date(2026, 1, 10),
        to_account_id=ctx.other_account.id,
    )

    # when
    from_ledger = await _ledger(db, ctx)
    to_ledger = await _ledger(db, ctx, ctx.other_account.id)

    # then: 같은 거래가 양쪽에 1행씩, 부호만 반대
    assert [i.id for i in from_ledger.items] == [tx.id]
    assert [i.id for i in to_ledger.items] == [tx.id]
    assert from_ledger.items[0].signed_amount == Decimal("-20000")
    assert to_ledger.items[0].signed_amount == Decimal("20000")

    # then: 잔액도 각 계좌 관점으로 반영 (상대 통장 시작잔액은 0)
    assert from_ledger.items[0].balance_after == START_BALANCE - 20000
    assert to_ledger.items[0].balance_after == Decimal("20000")


async def test_D1_5_평가조정은_방향대로_부호가_붙는다(db, ctx):
    """INV-E(평가조정 부호) — 수동자산 통장의 INCREASE/DECREASE.

    평가조정은 현금 유입 없이 가치만 증감시키므로 방향 플래그가 부호를 결정한다.
    """
    # given: 수동자산 통장(시작잔액 0)에 증가 500,000 → 감소 100,000
    await _create(
        db, ctx, tx_type=TxType.VALUATION, amount="500000", tx_date=date(2026, 1, 10),
        account_id=ctx.manual_asset.id, valuation_direction=ValuationDirection.INCREASE,
    )
    await _create(
        db, ctx, tx_type=TxType.VALUATION, amount="100000", tx_date=date(2026, 1, 20),
        account_id=ctx.manual_asset.id, valuation_direction=ValuationDirection.DECREASE,
    )

    # when
    page = await _ledger(db, ctx, ctx.manual_asset.id)

    # then: 최신(감소)이 첫 행
    assert page.items[0].signed_amount == Decimal("-100000")
    assert page.items[0].balance_after == Decimal("400000")
    assert page.items[1].signed_amount == Decimal("500000")
    assert page.items[1].balance_after == Decimal("500000")


# ── D1-6. 깨진/조작된 커서 (계약 확인 — 현재 동작 박제) ──────────────────
#
# `_split_ledger_cursor`(carry 분리)와 `_cursor_after`(3-tuple 파싱) 둘 다 파싱에
# 실패하면 **예외 없이 조용히 None 을 리턴**한다. 즉 잘못된 커서는 거부되지 않고
# "커서 없음"으로 취급돼 1페이지가 돌아온다. 계약 문서엔 이 분기가 안 적혀 있어
# 실측으로 확정한다.


async def test_D1_6a_깨진_커서는_거부되지_않고_첫_페이지로_되돌아간다(db, ctx):
    """조용한 fallback — 400 이 아니라 1페이지. 클라이언트는 중복 행을 받는다."""
    # given: 거래 4건, 2건씩 페이징
    for day in range(1, 5):
        await _expense(db, ctx, "1000", date(2026, 1, day))
    first = await _ledger(db, ctx, limit=2)
    assert first.has_next

    # when: 커서 자리에 쓰레기를 넣는다
    broken = await _ledger(db, ctx, cursor="garbage", limit=2)

    # then: 예외 없이 1페이지와 동일한 행 (조용히 처음으로 되돌아감)
    assert [i.id for i in broken.items] == [i.id for i in first.items]
    assert [i.balance_after for i in broken.items] == [
        i.balance_after for i in first.items
    ]


async def test_D1_6b_carry_만_깨지면_커서_전체가_무효화되고_잔액은_재계산된다(db, ctx):
    """carry 파싱 실패 시 `_split_ledger_cursor` 가 커서 전체를 그대로 넘겨
    `_cursor_after` 까지 실패한다 → 페이지는 처음으로 가지만 잔액은 재계산되어 정확하다.
    """
    # given
    for day in range(1, 5):
        await _expense(db, ctx, "1000", date(2026, 1, day))
    first = await _ledger(db, ctx, limit=2)
    valid_cursor = first.next_cursor

    # when: 정상 커서의 carry 자리만 숫자가 아닌 값으로 바꾼다
    base, _, _carry = valid_cursor.rpartition("|")
    tampered = await _ledger(db, ctx, cursor=f"{base}|not-a-number", limit=2)

    # then: 1페이지로 되돌아가되 잔액 기준점은 서버가 다시 계산한 값
    assert [i.id for i in tampered.items] == [i.id for i in first.items]
    assert tampered.items[0].balance_after == first.items[0].balance_after


async def test_D1_6c_carry_숫자를_바꾸면_그_값이_잔액_기준점이_된다(db, ctx):
    """⚪ 의도된 한계 — carry 가 숫자로 파싱되기만 하면 서버는 검증 없이 그대로 쓴다.

    잔액 기준점을 클라이언트가 정할 수 있다는 뜻. 자기 화면만 틀어지는 read-only
    경로라 피해는 제한적이지만, "잔액은 서버가 계산한다"는 신뢰와는 어긋난다.
    """
    # given
    for day in range(1, 5):
        await _expense(db, ctx, "1000", date(2026, 1, day))
    first = await _ledger(db, ctx, limit=2)
    base, _, real_carry = first.next_cursor.rpartition("|")

    # when: carry 만 엉뚱한 숫자로 바꾼다
    tampered = await _ledger(db, ctx, cursor=f"{base}|999999", limit=2)
    honest = await _ledger(db, ctx, cursor=first.next_cursor, limit=2)

    # then: 행은 같은데 잔액만 조작값 기준으로 밀린다
    assert [i.id for i in tampered.items] == [i.id for i in honest.items]
    assert honest.items[0].balance_after == Decimal(real_carry)
    assert tampered.items[0].balance_after == Decimal("999999")
