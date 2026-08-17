"""매도내역 수정 경로 — 순서 불변식 + 행 식별자 (TDD/RED 선행).

Stage 3 은 매매손익 카드에서 매도 거래를 직접 수정할 수 있게 만든다.
그 화면이 열리면 "매도 날짜를 매수보다 앞으로 옮기는" 편집이 손쉬워지는데,
현재 replay 는 최종 수량만 검사하므로 중간 시점 음수를 못 잡는다.

**도출한 불변식** — `_recompute_realized_pnl` 의 계약("매도시점 누적 이동평균으로
실현손익을 재박제")이 성립하려면 **매도 시점에 보유수량이 있어야** 한다.
없으면 `running_avg = 0` 이 되어 매도금액 전액이 이익으로 박제된다(원가 0).

    INV: 시간순 replay 중 어느 SELL 시점에도 보유수량이 음수가 되어서는 안 된다.

기존 검사는 replay 종료 후 `remaining_qty < 0` 뿐이라, 뒤따르는 매수가 충분하면
중간의 허위 손익이 그대로 남는다.

| # | 시나리오 |
|---|---|
| 1 | 매도가 매수보다 앞서면 거부된다 (최종 수량이 양수여도) |
| 2 | 거부되면 롤백돼 기존 실현손익·평단이 그대로다 |
| 3 | 최종 수량이 음수면 거부된다 (기존 동작 유지) |
| 4 | 매매손익 행에 종목 식별자(id/code/market)가 담긴다 |
| 5 | 전량매도로 사라진 종목의 매도를 수정하면 종목이 부활한다 |

5 가 Stage 3 의 존재 이유다 — 전량매도하면 종목 화면에 못 들어가 수정할 방법이
없었고, 그래서 매매손익 카드에서 바로 고칠 수 있게 만든다.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.core.exceptions import CustomException
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
from tests.fixtures.factory import (
    PortfolioContext,
    seed_portfolio_context,
    token_for,
)


@pytest_asyncio.fixture
async def ctx(db) -> PortfolioContext:
    return await seed_portfolio_context(db)


async def _new_item(db, ctx: PortfolioContext):
    res = await service.create_portfolio(
        db,
        ctx.household,
        PortfolioCreateRequest(
            name="테스트종목", code="005930", market=Market.KRX_KOSPI,
            currentPrice=Decimal("1000"), accountId=ctx.account.id,
        ),
    )
    return res.id


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


async def _txs(db, item_id, pt_type: str):
    rows = await PortfolioTransactionRepository(db).find_active_by_item_id(item_id)
    return [t for t in rows if t.pt_type == pt_type]


# =========================================================
# 1~3. 순서 불변식
# =========================================================


async def test_매도가_매수보다_앞서면_거부된다(db, ctx):
    """최종 수량이 양수여도 중간 시점에 보유가 없으면 안 된다.

    허용하면 그 매도는 running_avg=0 으로 계산돼 매도금액 전액이 이익으로 박제된다.
    """
    # given: 3월 매수 10주, 4월 매도 5주 (정상)
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 3, 1))
    await _sell(db, ctx, item_id, qty="5", price="1500", tx_date=date(2026, 4, 1))
    sell_tx = (await _txs(db, item_id, "SELL"))[0]

    # when: 매도 날짜를 매수보다 앞(1월)으로 옮긴다 — 최종 수량은 여전히 5주로 양수
    with pytest.raises(CustomException):
        await service.update_portfolio_transaction(
            db, ctx.household, sell_tx.id,
            PortfolioTxUpdateRequest(txDate=date(2026, 1, 1)),
        )


async def test_거부되면_거래가_바뀌지_않고_롤백된다(db, client, ctx):
    """API 레벨로 검증하는 이유 — 롤백은 요청 경계(`get_db`)에서 일어난다.

    `update_portfolio_transaction` 은 필드를 먼저 flush 한 뒤 replay 로 검증하므로,
    거부 시 이미 바뀐 tx_date 가 남지 않으려면 요청 단위 롤백이 실제로 돌아야 한다.
    서비스 함수를 한 세션에서 직접 부르는 테스트로는 이걸 증명할 수 없다
    (rollback 이 셋업 데이터까지 되돌린다).
    """
    # given: 커밋된 상태여야 다른 커넥션(요청)에서 보인다
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 3, 1))
    await _sell(db, ctx, item_id, qty="5", price="1500", tx_date=date(2026, 4, 1))
    sell_tx = (await _txs(db, item_id, "SELL"))[0]
    sell_id, before_pnl, before_date = sell_tx.id, sell_tx.realized_pnl, sell_tx.tx_date
    await db.commit()

    headers = {
        "Authorization": f"Bearer {token_for(ctx.user)}",
        "X-Household-Id": str(ctx.household.id),
    }

    # when: 매도를 매수보다 앞 날짜로 (거부되어야 함)
    res = await client.put(
        f"/portfolio/transactions/{sell_id}",
        json={"txDate": "2026-01-01"},
        headers=headers,
    )

    # then: 400 + 거래가 그대로
    assert res.status_code == 400
    db.expire_all()
    after = (await _txs(db, item_id, "SELL"))[0]
    assert after.tx_date == before_date
    assert after.realized_pnl == before_pnl


async def test_최종_수량이_음수가_되면_거부된다(db, ctx):
    """기존 동작 유지 — 보유보다 많이 팔 수 없다."""
    # given: 10주 보유, 5주 매도
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 3, 1))
    await _sell(db, ctx, item_id, qty="5", price="1500", tx_date=date(2026, 4, 1))
    sell_tx = (await _txs(db, item_id, "SELL"))[0]

    # when: 매도 수량을 20주로 늘림
    with pytest.raises(CustomException):
        await service.update_portfolio_transaction(
            db, ctx.household, sell_tx.id,
            PortfolioTxUpdateRequest(quantity=Decimal("20")),
        )


# =========================================================
# 4. 행 식별자
# =========================================================


async def test_매매손익_행에_종목_식별자가_담긴다(db, ctx):
    """계좌 단위 응답은 여러 종목의 매도가 섞인다 — 행만 보고 종목을 특정할 수 있어야
    카드 탭으로 수정 시트를 열고 갱신 대상을 정할 수 있다."""
    # given
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 3, 1))
    await _sell(db, ctx, item_id, qty="5", price="1500", tx_date=date(2026, 4, 1))

    # when
    result = await service.get_realized_pnl_by_account(
        db, ctx.household, ctx.account.id,
    )

    # then
    row = result.rows[0]
    assert row.portfolio_item_id == item_id
    assert row.code == "005930"
    assert row.market == Market.KRX_KOSPI
    assert row.name == "테스트종목"


# =========================================================
# 5. 전량매도된 종목의 매도 수정 → 부활
# =========================================================


async def test_전량매도로_사라진_종목의_매도를_수정하면_종목이_부활한다(db, ctx):
    """Stage 3 의 존재 이유 — 전량매도하면 종목 화면 진입이 막혀 수정할 길이 없었다."""
    # given: 10주 전량 매도 → 종목 soft delete
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 3, 1))
    await _sell(db, ctx, item_id, qty="10", price="1500", tx_date=date(2026, 4, 1))
    assert await PortfolioItemRepository(db).find_by_id(item_id) is None  # 조회 안 됨

    sell_tx = (await _txs(db, item_id, "SELL"))[0]

    # when: 매도 수량을 6주로 정정 (실수로 전량 입력했던 케이스)
    await service.update_portfolio_transaction(
        db, ctx.household, sell_tx.id, PortfolioTxUpdateRequest(quantity=Decimal("6")),
    )

    # then: 4주 보유로 부활
    item = await PortfolioItemRepository(db).find_by_id(item_id)
    assert item is not None
    assert item.quantity == Decimal("4.0000")
    assert item.avg_price == Decimal("1000.00")
