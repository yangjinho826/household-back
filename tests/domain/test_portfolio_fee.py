"""매매 수수료(fee) — 평단 가산 / 실현손익 차감 / 매매현금 반영 (TDD/RED 선행).

**공개 계약** — 증권사 매매 계산과 동일하게:

| 대상 | 규칙 |
|---|---|
| 매수 수수료 | 매수원가에 가산 → 평단(`avg_price`)이 올라간다 |
| 매도 수수료 | 실현손익(`realized_pnl`)에서 차감된다 |
| 매매현금 | 매수는 `금액+수수료` 출금, 매도는 `금액−수수료` 입금 |
| 수익률 분모 | `realized_cost_basis` = 매도시점 평단×수량. 평단에 매수수수료가 이미
|            | 섞여 있으므로 분모에도 매수수수료가 포함된다(증권사 정의와 동일) |
| 기존 데이터 | `fee=0` 이라 모든 값이 도입 전과 같아야 한다 |

| # | 시나리오 |
|---|---|
| 1 | 매수 수수료가 평단에 섞인다 |
| 2 | 매도 수수료가 실현손익에서 빠진다 |
| 3 | fee=0 이면 기존과 값이 완전히 동일 (회귀) |
| 4 | 매매현금 — 매수 금액+fee 출금, 매도 금액−fee 입금 |
| 5 | realized_cost_basis 에 매수수수료가 포함돼 수익률 분모가 일관 |
| 6 | fee 를 수정하면 평단·실현손익이 재계산된다 |
| 7 | fee 음수 거부 (경계 -1 / 0) |
| 8 | 전량매도 후 재매수 — 매수 fee 가 새 평단에만 반영 |
| 9 | settlement_amount — 매수=금액+fee, 매도=금액−fee |
| 10 | 요약 total_fee = 기간 내 매도 수수료 합계 |
| 11 | asof_holdings 평단에도 매수 fee 반영 (스냅샷 ↔ 종목 일치) |
| 12 | 매도후 재매수해도 스냅샷 평단 = 종목 평단 (이동평균 통일) |
| 13 | as_of 이후 거래는 스냅샷에 섞이지 않는다 |

11 이 중요한 이유: `asof_holdings_by_account` 는 스냅샷 박제용 별도 집계 경로다.
replay 에만 fee 를 넣으면 박제된 평단과 화면 평단이 갈린다.
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
from tests.fixtures.factory import PortfolioContext, seed_portfolio_context


@pytest_asyncio.fixture
async def ctx(db) -> PortfolioContext:
    return await seed_portfolio_context(db)


async def _new_item(db, ctx: PortfolioContext, *, current_price: str = "1000"):
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


async def _buy(db, ctx, item_id, *, qty: str, price: str, tx_date: date, fee: str = "0"):
    return await service.buy(
        db, ctx.household, item_id,
        PortfolioBuyRequest(
            quantity=Decimal(qty), price=Decimal(price), txDate=tx_date,
            fee=Decimal(fee),
        ),
    )


async def _sell(db, ctx, item_id, *, qty: str, price: str, tx_date: date, fee: str = "0"):
    return await service.sell(
        db, ctx.household, item_id,
        PortfolioSellRequest(
            quantity=Decimal(qty), sellPrice=Decimal(price), txDate=tx_date,
            fee=Decimal(fee),
        ),
    )


async def _item(db, item_id):
    return await PortfolioItemRepository(db).find_by_id(item_id)


async def _sell_rows(db, item_id):
    txs = await PortfolioTransactionRepository(db).find_active_by_item_id(item_id)
    return [t for t in txs if t.pt_type == "SELL"]


# =========================================================
# 1~2. 평단 가산 / 실현손익 차감
# =========================================================


async def test_매수_수수료가_평단에_가산된다(db, ctx):
    # given / when: 10주 @1000 + 수수료 500
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 1, 1), fee="500")

    # then: 원가 10*1000 + 500 = 10500, 수량 10 → 평단 1050
    item = await _item(db, item_id)
    assert item.quantity == Decimal("10.0000")
    assert item.avg_price == Decimal("1050.00")


async def test_매도_수수료가_실현손익에서_차감된다(db, ctx):
    # given: 10주 @1000 매수(수수료 0) → 평단 1000
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 1, 1))

    # when: 10주 @1500 매도, 수수료 700
    await _sell(db, ctx, item_id, qty="10", price="1500", tx_date=date(2026, 2, 1), fee="700")

    # then: (1500-1000)*10 - 700 = 4300
    sells = await _sell_rows(db, item_id)
    assert sells[0].realized_pnl == Decimal("4300.00")


# =========================================================
# 3. 회귀 — fee=0 이면 도입 전과 동일
# =========================================================


async def test_수수료가_0이면_기존_계산과_동일하다(db, ctx):
    """fee 컬럼 도입이 기존 데이터의 값을 바꾸지 않는다."""
    # given: 100주 @1000 → 50주 @1500 매도 → 50주 @2000 재매수 (전부 fee 0)
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="100", price="1000", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, item_id, qty="50", price="1500", tx_date=date(2026, 2, 1))
    await _buy(db, ctx, item_id, qty="50", price="2000", tx_date=date(2026, 3, 1))

    # then: fee 도입 전과 같은 값 (test_portfolio_pnl D2-1 과 동일 기대)
    item = await _item(db, item_id)
    assert item.quantity == Decimal("100.0000")
    assert item.avg_price == Decimal("1500.00")

    sells = await _sell_rows(db, item_id)
    assert sells[0].realized_pnl == Decimal("25000.00")
    assert sells[0].realized_cost_basis == Decimal("50000.00")


# =========================================================
# 4. 매매현금
# =========================================================


async def test_매매현금은_매수에_수수료를_더하고_매도에서_뺀다(db, ctx):
    """계좌 현금 = start_balance - Σ(매수금액+fee) + Σ(매도금액-fee)."""
    # given
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 1, 1), fee="500")
    await _sell(db, ctx, item_id, qty="5", price="1200", tx_date=date(2026, 2, 1), fee="300")

    # when
    sums = await PortfolioTransactionRepository(db).sum_for_account(ctx.account.id)

    # then: 매수 10*1000+500 = 10500 / 매도 5*1200-300 = 5700
    assert sums["buy"] == Decimal("10500.00")
    assert sums["sell"] == Decimal("5700.00")


# =========================================================
# 5. 수익률 분모 일관성
# =========================================================


async def test_실현손익_원가에_매수수수료가_포함된다(db, ctx):
    """분자(실현손익)만 net 이고 분모가 gross 면 수익률 의미가 깨진다.

    매수 수수료가 평단에 들어가므로 realized_cost_basis 에도 자동 포함돼야 한다.
    """
    # given: 10주 @1000 + 매수수수료 500 → 평단 1050
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 1, 1), fee="500")

    # when: 전량 매도 (매도수수료 0)
    await _sell(db, ctx, item_id, qty="10", price="1500", tx_date=date(2026, 2, 1))

    # then: 원가 = 1050*10 = 10500 (매수수수료 포함), 손익 = 15000-10500 = 4500
    sells = await _sell_rows(db, item_id)
    assert sells[0].realized_cost_basis == Decimal("10500.00")
    assert sells[0].realized_pnl == Decimal("4500.00")


# =========================================================
# 6. fee 수정 → 재계산
# =========================================================


async def test_수수료를_수정하면_평단과_실현손익이_재계산된다(db, ctx):
    # given: 매수 fee 0 으로 넣었다가
    item_id = await _new_item(db, ctx)
    buy_res = await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 1, 1))
    assert buy_res.avg_price == Decimal("1000.00")

    txs = await PortfolioTransactionRepository(db).find_active_by_item_id(item_id)
    buy_tx = next(t for t in txs if t.pt_type == "BUY")

    # when: 뒤늦게 수수료 500 으로 정정
    await service.update_portfolio_transaction(
        db, ctx.household, buy_tx.id, PortfolioTxUpdateRequest(fee=Decimal("500")),
    )

    # then: 평단 재계산 1050
    item = await _item(db, item_id)
    assert item.avg_price == Decimal("1050.00")


# =========================================================
# 7. 음수 거부
# =========================================================


@pytest.mark.parametrize("fee", ["-1", "-0.01"])
async def test_음수_수수료는_거부된다(fee):
    with pytest.raises(CustomException):
        PortfolioBuyRequest(
            quantity=Decimal("1"), price=Decimal("1000"), fee=Decimal(fee),
        )


async def test_수수료_0은_허용된다():
    req = PortfolioBuyRequest(
        quantity=Decimal("1"), price=Decimal("1000"), fee=Decimal("0"),
    )
    assert req.fee == Decimal("0")


# =========================================================
# 8. 전량매도 후 재매수
# =========================================================


async def test_부분매도_후_재매수하면_새_매수_수수료만_평단에_더해진다(db, ctx):
    """매도 수수료는 원가에 남지 않는다 — 이미 판 수량의 비용이 남은 보유분
    평단을 올리면 안 되기 때문. 새 매수의 수수료만 새 원가에 들어간다.

    (전량매도는 종목이 soft delete 돼 같은 item_id 로 재매수가 불가능하다 —
    그건 제품 동작이라 여기서는 부분매도로 같은 성질을 검증한다.)
    """
    # given: 10주 @1000 fee 200 → 원가 10200, 평단 1020
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 1, 1), fee="200")

    # when: 5주 부분매도(fee 100) 후 5주 @2000 재매수(fee 300)
    await _sell(db, ctx, item_id, qty="5", price="1500", tx_date=date(2026, 2, 1), fee="100")
    await _buy(db, ctx, item_id, qty="5", price="2000", tx_date=date(2026, 3, 1), fee="300")

    # then: 남은 원가 1020*5=5100 + 신규 10000+300 = 15400, 수량 10 → 평단 1540
    #       매도 수수료 100 은 원가에 남지 않는다
    item = await _item(db, item_id)
    assert item.quantity == Decimal("10.0000")
    assert item.avg_price == Decimal("1540.00")


# =========================================================
# 9~10. 응답 필드
# =========================================================


async def test_거래내역_응답에_수수료와_정산금액이_담긴다(db, ctx):
    # given
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 1, 1), fee="500")
    await _sell(db, ctx, item_id, qty="5", price="1200", tx_date=date(2026, 2, 1), fee="300")

    # when
    page = await service.list_item_transactions_cursor(
        db, ctx.household, item_id, None, 30,
    )
    by_type = {i.pt_type: i for i in page.items}

    # then: 매수 정산 = 금액+fee, 매도 정산 = 금액-fee
    assert by_type["BUY"].fee == Decimal("500.00")
    assert by_type["BUY"].total == Decimal("10000.00")
    assert by_type["BUY"].settlement_amount == Decimal("10500.00")

    assert by_type["SELL"].fee == Decimal("300.00")
    assert by_type["SELL"].total == Decimal("6000.00")
    assert by_type["SELL"].settlement_amount == Decimal("5700.00")


async def test_매매손익_요약에_수수료_합계가_담긴다(db, ctx):
    """gross(매도금액)와 net(실현손익)이 한 화면에 섞이므로 제비용을 따로 보여준다."""
    # given: 매도 2건, 수수료 300 + 200
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="20", price="1000", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, item_id, qty="5", price="1200", tx_date=date(2026, 2, 1), fee="300")
    await _sell(db, ctx, item_id, qty="5", price="1300", tx_date=date(2026, 3, 1), fee="200")

    # when
    result = await service.get_realized_pnl_by_item(db, ctx.household, item_id)

    # then
    assert result.summary.total_fee == Decimal("500.00")


# =========================================================
# 11. 스냅샷 경로 정합
# =========================================================


async def test_스냅샷용_보유집계_평단에도_매수수수료가_반영된다(db, ctx):
    """asof_holdings_by_account 는 스냅샷 박제용 별도 집계 경로다.

    replay 에만 fee 를 넣으면 박제 평단과 종목 평단이 갈린다.
    """
    # given: 10주 @1000 + 수수료 500 → 평단 1050
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="1000", tx_date=date(2026, 1, 1), fee="500")

    # when
    holdings = await PortfolioTransactionRepository(db).asof_holdings_by_account(
        ctx.account.id, date(2026, 12, 31),
    )

    # then: 종목 평단과 동일
    item = await _item(db, item_id)
    assert len(holdings) == 1
    assert holdings[0]["avg_cost"] == item.avg_price == Decimal("1050.00")
    assert holdings[0]["cost"] == Decimal("10500.00")


async def test_매도후_재매수한_종목도_스냅샷_평단이_종목_평단과_같다(db, ctx):
    """단순평균(Σ매수금액 / Σ매수수량)으로 집계하면 매도가 평단을 되돌려버린다.

    매수 10@100 → 매도 5 → 매수 5@200
      이동평균(종목): 원가 1,500 / 10주 → 150
      단순평균(집계): 2,000 / 15주    → 133.33
    스냅샷은 자산 추이 그래프의 과거 구간을 박제하므로, 두 값이 갈리면
    그래프가 화면의 종목 평단과 다른 이야기를 하게 된다.
    """
    # given
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="100", tx_date=date(2026, 1, 1))
    await service.sell(
        db, ctx.household, item_id,
        PortfolioSellRequest(
            quantity=Decimal("5"), sellPrice=Decimal("120"), txDate=date(2026, 2, 1),
        ),
    )
    await _buy(db, ctx, item_id, qty="5", price="200", tx_date=date(2026, 3, 1))

    # when
    holdings = await PortfolioTransactionRepository(db).asof_holdings_by_account(
        ctx.account.id, date(2026, 12, 31),
    )

    # then
    item = await _item(db, item_id)
    assert item.avg_price == Decimal("150.00")
    assert holdings[0]["quantity"] == Decimal("10")
    assert holdings[0]["avg_cost"] == item.avg_price
    assert holdings[0]["cost"] == Decimal("1500.00")


async def test_as_of_이후_거래는_스냅샷_평단에_섞이지_않는다(db, ctx):
    """박제는 그 시점까지의 사실만 담아야 한다 — replay 로 바꿔도 컷은 유지된다."""
    # given: 1월 매수 후 3월에 비싼 매수
    item_id = await _new_item(db, ctx)
    await _buy(db, ctx, item_id, qty="10", price="100", tx_date=date(2026, 1, 1))
    await _buy(db, ctx, item_id, qty="10", price="500", tx_date=date(2026, 3, 1))

    # when: 2월 말 기준
    holdings = await PortfolioTransactionRepository(db).asof_holdings_by_account(
        ctx.account.id, date(2026, 2, 28),
    )

    # then: 3월 매수는 없는 셈
    assert holdings[0]["quantity"] == Decimal("10")
    assert holdings[0]["avg_cost"] == Decimal("100.00")
