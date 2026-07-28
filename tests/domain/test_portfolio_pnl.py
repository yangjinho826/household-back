"""D2. 포트폴리오 실현손익/평단 정합 (명세 기반 사후검증).

**도출한 불변식** — 공개계약에서 독립 도출:
`_recompute_realized_pnl` docstring 은 "거래 수정/삭제로 평단이 바뀌면 과거 SELL 의
박제값이 틀어지므로 매도시점 누적 이동평균으로 다시 계산한다"를 계약으로 선언한다.
`_recalc_item_from_transactions` 는 "매도 후 재매수도 정확히 반영"을 보장한다.
두 계약을 합치면 다음이 성립해야 한다:

    INV: 활성 거래 집합이 같으면 각 SELL 의 realized_pnl 과 종목의 quantity/avg_price 는
         같다 — 재계산이 언제 트리거됐는지와 무관하게.

이 불변식이 깨지면 "같은 데이터인데 조회 시점에 따라 손익이 다르다"가 되어
돈 정합성 결함이다.

**두 진실 원천**(RED 의 뿌리):
| 경로 | 계산 | 순서 기준 |
|---|---|---|
| `sell()` | incremental — 그 순간의 `item.avg_price` | 입력 순서 (날짜 무관) |
| `_recompute_realized_pnl()` | replay — 처음부터 재계산 | `tx_date asc` (repository.py:236) |
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest_asyncio

from app.domain.portfolio import service
from app.domain.portfolio.enum import Market
from app.domain.portfolio.repository import (
    PortfolioItemRepository,
    PortfolioTransactionRepository,
)
from app.domain.portfolio.schema import (
    PortfolioBuyRequest,
    PortfolioCreateRequest,
    PortfolioSellRequest,
    PortfolioTxUpdateRequest,
)
from tests.fixtures.factory import PortfolioContext, seed_portfolio_context


@pytest_asyncio.fixture
async def ctx(db) -> PortfolioContext:
    return await seed_portfolio_context(db)


async def _new_item(db, ctx: PortfolioContext, *, current_price: str = "1000"):
    """종목 등록 — 메타만(qty=0, avg=0). 매수는 buy() 로."""
    response = await service.create_portfolio(
        db,
        ctx.household,
        PortfolioCreateRequest(
            name="테스트종목",
            code="005930",
            market=Market.KRX_KOSPI,
            currentPrice=Decimal(current_price),
            accountId=ctx.account.id,
        ),
    )
    return response.id


async def _buy(db, ctx, item_id, *, qty: str, price: str, tx_date: date):
    return await service.buy(
        db, ctx.household, item_id,
        PortfolioBuyRequest(quantity=Decimal(qty), price=Decimal(price), txDate=tx_date),
    )


async def _sell(db, ctx, item_id, *, qty: str, price: str, tx_date: date):
    return await service.sell(
        db, ctx.household, item_id,
        PortfolioSellRequest(
            quantity=Decimal(qty), sellPrice=Decimal(price), txDate=tx_date,
        ),
    )


async def _sell_rows(db, item_id):
    """해당 종목의 활성 SELL 거래 (tx_date asc)."""
    txs = await PortfolioTransactionRepository(db).find_active_by_item_id(item_id)
    return [t for t in txs if t.pt_type == "SELL"]


async def _item(db, item_id):
    return await PortfolioItemRepository(db).find_by_id(item_id)


async def test_D2_1_매도_후_재매수하면_평단이_이동평균으로_반영된다(db, ctx):
    """계약: '매도 시점 평단으로 원가를 차감하므로 매도 후 재매수도 정확히 반영'.

    매도는 평단을 바꾸지 않는다 — 남은 원가는 평단 비율로만 줄어든다.
    """
    # given: 100주 @1000 매수 → 평단 1000
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="100", price="1000", tx_date=date(2026, 1, 1))

    # when: 50주 매도(평단 불변) 후 50주 @2000 재매수
    await _sell(db, ctx, item_id, qty="50", price="1500", tx_date=date(2026, 2, 1))
    await _buy(db, ctx, item_id, qty="50", price="2000", tx_date=date(2026, 3, 1))

    # then: 남은 원가 50*1000 + 신규 50*2000 = 150000, 수량 100 → 평단 1500
    item = await _item(db, item_id)
    assert item.quantity == Decimal("100.0000")
    assert item.avg_price == Decimal("1500.00")


async def test_D2_2_과거_매수를_수정하면_과거_매도의_실현손익이_재박제된다(db, ctx):
    """계약: '거래 수정으로 평단이 바뀌면 과거 SELL 의 박제값을 다시 계산한다'."""
    # given: 100주 @1000 매수 후 50주 @1500 매도 → 실현손익 (1500-1000)*50 = 25000
    item_id = await _new_item(db, ctx)
    buy_response = await _buy(
        db, ctx, item_id, qty="100", price="1000", tx_date=date(2026, 1, 1),
    )
    await _sell(db, ctx, item_id, qty="50", price="1500", tx_date=date(2026, 2, 1))

    sells = await _sell_rows(db, item_id)
    assert sells[0].realized_pnl == Decimal("25000.00")

    # when: 그 매수의 단가를 1000 → 1200 으로 수정
    buy_tx = [
        t for t in await PortfolioTransactionRepository(db).find_active_by_item_id(item_id)
        if t.pt_type == "BUY"
    ][0]
    await service.update_portfolio_transaction(
        db, ctx.household, buy_tx.id, PortfolioTxUpdateRequest(price=Decimal("1200")),
    )

    # then: 매도 실현손익이 (1500-1200)*50 = 15000 으로 재박제
    sells = await _sell_rows(db, item_id)
    assert sells[0].realized_pnl == Decimal("15000.00")
    assert buy_response is not None


async def test_D2_3_백데이팅_매수는_기존_매도의_실현손익을_재계산하지_않는다(db, ctx):
    """🔴 INV 위반 후보 — 과거 날짜 매수를 나중에 입력한 경우.

    `buy()` 는 incremental(입력 순서) 이라 이미 박제된 SELL 을 건드리지 않는다.
    그러나 replay(`tx_date asc`) 기준으로는 이 매수가 SELL **앞**에 와야 하므로
    매도시점 평단이 달라진다 → 저장된 값과 replay 값이 갈린다.
    """
    # given: 100주 @1000 매수(01-01) → 50주 @1500 매도(03-01) → 실현손익 25000
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="100", price="1000", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, item_id, qty="50", price="1500", tx_date=date(2026, 3, 1))

    sells = await _sell_rows(db, item_id)
    assert sells[0].realized_pnl == Decimal("25000.00")

    # when: 매도보다 앞선 날짜(02-01)의 매수를 뒤늦게 입력
    await _buy(db, ctx, item_id, qty="100", price="2000", tx_date=date(2026, 2, 1))

    # then(계약): 매도시점(03-01) 평단은 (100*1000 + 100*2000)/200 = 1500 이어야 하고
    #             실현손익은 (1500-1500)*50 = 0 이어야 한다.
    sells = await _sell_rows(db, item_id)
    assert sells[0].realized_pnl == Decimal("0.00")

    # 종목 평단도 replay 기준이어야 한다: 매도 후 원가 225000 / 수량 150 = 1500
    item = await _item(db, item_id)
    assert item.quantity == Decimal("150.0000")
    assert item.avg_price == Decimal("1500.00")


async def test_D2_4_메모만_수정해도_실현손익이_바뀌면_INV_위반이다(db, ctx):
    """🔴 결정적 증거 — 거래 집합이 그대로인데 값이 달라지는지.

    D2-3 상태에서 아무 금액도 바꾸지 않는 수정(memo)을 넣으면
    `update_portfolio_transaction` 이 무조건 `_recalc_item_from_transactions` 를 태운다.
    INV 가 성립하면 재계산 전후 값이 같아야 한다.
    """
    # given: D2-3 과 동일한 거래 집합(백데이팅 매수 포함)
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="100", price="1000", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, item_id, qty="50", price="1500", tx_date=date(2026, 3, 1))
    await _buy(db, ctx, item_id, qty="100", price="2000", tx_date=date(2026, 2, 1))

    sells = await _sell_rows(db, item_id)
    pnl_before = sells[0].realized_pnl
    item = await _item(db, item_id)
    avg_before = item.avg_price

    # when: 금액과 무관한 memo 만 수정 → 재계산만 트리거
    first_buy = [
        t for t in await PortfolioTransactionRepository(db).find_active_by_item_id(item_id)
        if t.pt_type == "BUY"
    ][0]
    await service.update_portfolio_transaction(
        db, ctx.household, first_buy.id, PortfolioTxUpdateRequest(memo="메모만 변경"),
    )

    # then: 거래 집합이 동일하므로 값이 그대로여야 한다
    sells = await _sell_rows(db, item_id)
    item = await _item(db, item_id)
    assert sells[0].realized_pnl == pnl_before
    assert item.avg_price == avg_before
