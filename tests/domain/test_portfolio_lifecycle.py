"""D4. 종목 수량·상태 전이 (명세 기반 사후검증).

**공개계약** (`portfolio/service.py`)
- `_recalc_item_from_transactions` docstring — "매도가 매수보다 많으면 BAD_REQUEST",
  "거래 수정/삭제로 수량이 0→양수면 종목 부활, 양수→0이면 소멸(전량매도와 동일)"
- `sell` docstring — "매도 (부분/전량). 전량 시 portfolio_items soft delete, 응답 None"

D2 에서 `buy`/`sell` 의 incremental 계산을 걷어내고 replay 로 통일했으므로 소멸·부활
경계가 전부 replay 결과(`remaining_qty`)를 타게 됐다. 이 경계가 계약대로 도는지 확인한다.

**D4-2 가 D2 수정의 개선을 박제한다**: 수정 전 `sell()` 은 전량매도 시 `data_stat_cd` 만
DELETED 로 바꾸고 `quantity` 는 마지막 보유량을 그대로 남겼다(운영 DB 점검에서 죽은 종목
3건에 화석 수량이 실제로 남아 있었다). 이제는 replay 가 0 까지 맞춘다.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
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


async def _new_item(db, ctx: PortfolioContext):
    response = await service.create_portfolio(
        db,
        ctx.household,
        PortfolioCreateRequest(
            name="테스트종목",
            code="005930",
            market=Market.KRX_KOSPI,
            currentPrice=Decimal("1000"),
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


async def _item_any_status(db, item_id):
    """DELETED 종목까지 조회 — 소멸/부활 검증엔 상태 무관 조회가 필요하다."""
    return await PortfolioItemRepository(db).find_by_id_any_status(item_id)


async def _txs(db, item_id, pt_type: str | None = None):
    rows = await PortfolioTransactionRepository(db).find_active_by_item_id(item_id)
    return [t for t in rows if pt_type is None or t.pt_type == pt_type]


async def test_D4_1_보유수량보다_많이_매도하면_거부된다(db, ctx):
    """사전 검증 — 저장된 보유 수량을 넘는 매도는 거래를 만들지 않는다."""
    # given: 100주 보유
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="100", price="1000", tx_date=date(2026, 1, 1))

    # when / then
    with pytest.raises(CustomException) as exc:
        await _sell(db, ctx, item_id, qty="101", price="1500", tx_date=date(2026, 2, 1))
    assert exc.value.error_code == ErrorCode.BAD_REQUEST

    # then: 거부된 매도는 이력에 남지 않고 보유 수량도 그대로
    assert await _txs(db, item_id, "SELL") == []
    item = await _item_any_status(db, item_id)
    assert item.quantity == Decimal("100.0000")


async def test_D4_2_전량_매도하면_수량0으로_소멸하고_응답이_없다(db, ctx):
    """소멸 — replay 결과가 0 이면 soft delete. quantity 도 0 까지 맞춰져야 한다."""
    # given
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="100", price="1000", tx_date=date(2026, 1, 1))

    # when: 전량 매도
    response = await _sell(db, ctx, item_id, qty="100", price="1500", tx_date=date(2026, 2, 1))

    # then: 응답 None + DELETED + 수량 0(마지막 보유량이 화석으로 남지 않는다)
    assert response is None
    item = await _item_any_status(db, item_id)
    assert item.data_stat_cd == DataStatus.DELETED
    assert item.quantity == Decimal("0.0000")


async def test_D4_3_매수를_줄여_매도보다_적어지면_거부된다(db, ctx):
    """replay 안의 경계 — 수정 결과가 음수 수량이면 BAD_REQUEST."""
    # given: 100주 매수 후 80주 매도 (잔여 20)
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="100", price="1000", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, item_id, qty="80", price="1500", tx_date=date(2026, 2, 1))

    buy_tx = (await _txs(db, item_id, "BUY"))[0]

    # when: 매수를 50주로 줄이면 매도(80) 가 매수(50) 를 넘는다
    with pytest.raises(CustomException) as exc:
        await service.update_portfolio_transaction(
            db, ctx.household, buy_tx.id,
            PortfolioTxUpdateRequest(quantity=Decimal("50")),
        )
    assert exc.value.error_code == ErrorCode.BAD_REQUEST


async def test_D4_4_전량매도로_죽은_종목은_그_매도를_지우면_부활한다(db, ctx):
    """부활 — 수량이 0→양수로 돌아오면 종목이 다시 ACTIVE 가 된다."""
    # given: 전량 매도로 소멸시킨다
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="100", price="1000", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, item_id, qty="100", price="1500", tx_date=date(2026, 2, 1))

    dead = await _item_any_status(db, item_id)
    assert dead.data_stat_cd == DataStatus.DELETED

    sell_tx = (await _txs(db, item_id, "SELL"))[0]

    # when: 그 매도 이력을 삭제
    await service.delete_portfolio_transaction(db, ctx.household, sell_tx.id)

    # then: 매수만 남아 수량이 되살아나고 종목도 ACTIVE
    revived = await _item_any_status(db, item_id)
    assert revived.data_stat_cd == DataStatus.ACTIVE
    assert revived.quantity == Decimal("100.0000")
    assert revived.avg_price == Decimal("1000.00")
