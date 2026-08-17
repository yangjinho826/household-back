"""해외 종목 USD 거래 — 거래통화 병행 보관 (TDD/RED 선행).

**설계 계약**

| 축 | 규칙 |
|---|---|
| 진실 원천 | KRW 컬럼. 순자산·계좌잔액·스냅샷 합산은 전부 KRW 만 본다 |
| 거래통화 | `*_ccy` 컬럼에 병행 보관. 화면 표시와 종목 수익률 계산용 |
| 통화 판정 | 종목의 `market` 에서 도출 (NASDAQ/NYSE → USD). item 과 tx 가 갈리지 않게 |
| 환율 | 거래 시점 값을 tx 에 박제. 없으면 USD 매매 거부 |
| 레거시 | `price_ccy IS NULL` = 원화로만 기록된 과거 거래. ccy 지표는 NULL |

**왜 KRW 를 진실 원천으로 두는가** — `account/service.py` 의 `_summarize_holdings`,
`wealth/service.py`, `portfolio/repository.py` 가 `quantity * current_price` 를 통화
구분 없이 합산한다. 거래통화로 전환하면 달러와 원이 섞여 순자산이 조용히 틀린다.

**왜 레거시를 backfill 하지 않는가** — 기존 NASDAQ 거래의 `price` 는 이미 원화
환산값이고(실측 247,000~385,000), 원본 달러가와 당시 환율은 저장돼 있지 않다.
`price_ccy = price` 는 달러 칸에 원화를 넣는 것이고, `price / 현재환율` 은 과거
거래에 오늘 환율을 씌운 가짜 매수가다. 둘 다 화면에 거짓을 표시한다.

| # | 시나리오 |
|---|---|
| 1 | USD 매수 — price_ccy 원본과 fx_rate 박제, KRW price = price_ccy × fx |
| 2 | 환율이 없으면 USD 매매 거부 |
| 3 | KRW 종목은 currency=KRW / fx_rate=1 / price_ccy=price |
| 4 | ccy 평단은 달러 기준 이동평균 |
| 5 | 레거시 거래가 섞이면 ccy 평단은 NULL |
| 6 | 통화는 market 에서 도출된다 |
| 7 | 순자산 합산은 KRW 컬럼만 쓴다 |
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException
from app.domain.exchange_rate.enum import CurrencyCode
from app.domain.exchange_rate.model import CurrencyRate
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
)
from tests.fixtures.factory import PortfolioContext, seed_portfolio_context

USD_KRW = Decimal("1400.0000")


@pytest_asyncio.fixture
async def ctx(db) -> PortfolioContext:
    return await seed_portfolio_context(db)


@pytest_asyncio.fixture
async def fx(db):
    """USD/KRW 환율 1행 — USD 매매의 전제."""
    rate = CurrencyRate(
        base_currency=CurrencyCode.USD,
        quote_currency=CurrencyCode.KRW,
        rate=USD_KRW,
        data_stat_cd=DataStatus.ACTIVE,
    )
    db.add(rate)
    await db.flush()
    return rate


async def _new_item(db, ctx, *, market: Market, code: str, price: str = "100"):
    res = await service.create_portfolio(
        db,
        ctx.household,
        PortfolioCreateRequest(
            name="테스트종목", code=code, market=market,
            currentPrice=Decimal(price), accountId=ctx.account.id,
        ),
    )
    return res.id


async def _buy(db, ctx, item_id, *, qty: str, price: str, tx_date: date, fee: str = "0"):
    return await service.buy(
        db, ctx.household, item_id,
        PortfolioBuyRequest(
            quantity=Decimal(qty), price=Decimal(price), txDate=tx_date, fee=Decimal(fee),
        ),
    )


async def _txs(db, item_id):
    return await PortfolioTransactionRepository(db).find_active_by_item_id(item_id)


async def _item(db, item_id):
    return await PortfolioItemRepository(db).find_by_id(item_id)


# =========================================================
# 1~3. 저장 규칙
# =========================================================


async def test_USD_매수는_달러_원본과_환율을_박제한다(db, ctx, fx):
    """사용자는 달러로 입력한다. KRW 는 환율을 곱해 파생한다."""
    # given: 나스닥 종목
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")

    # when: 10주 @ $250 매수
    await _buy(db, ctx, item_id, qty="10", price="250", tx_date=date(2026, 3, 1))

    # then
    tx = (await _txs(db, item_id))[0]
    assert tx.currency == "USD"
    assert tx.price_ccy == Decimal("250.0000")
    assert tx.fx_rate == USD_KRW
    assert tx.price == Decimal("350000.00")  # 250 * 1400


async def test_환율이_없으면_USD_매매가_거부된다(db, ctx):
    """조용히 1 을 쓰면 순자산이 1/1400 로 찌그러진다."""
    # given: 환율 fixture 없음
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")

    # when / then
    with pytest.raises(CustomException):
        await _buy(db, ctx, item_id, qty="10", price="250", tx_date=date(2026, 3, 1))


async def test_국내_종목은_원화_그대로_기록된다(db, ctx, fx):
    # given
    item_id = await _new_item(db, ctx, market=Market.KRX_KOSPI, code="005930")

    # when
    await _buy(db, ctx, item_id, qty="10", price="70000", tx_date=date(2026, 3, 1))

    # then: 환율 곱셈 없음
    tx = (await _txs(db, item_id))[0]
    assert tx.currency == "KRW"
    assert tx.fx_rate == Decimal("1.0000")
    assert tx.price_ccy == Decimal("70000.0000")
    assert tx.price == Decimal("70000.00")


# =========================================================
# 4~5. ccy 트랙
# =========================================================


async def test_달러_평단은_달러_기준_이동평균이다(db, ctx, fx):
    """환율이 섞이지 않은 순수 종목 수익률을 내려면 달러로 따로 굴려야 한다."""
    # given / when: $200 10주 + $300 10주
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")
    await _buy(db, ctx, item_id, qty="10", price="200", tx_date=date(2026, 1, 1))
    await _buy(db, ctx, item_id, qty="10", price="300", tx_date=date(2026, 2, 1))

    # then: 달러 평단 250, 원화 평단은 350,000 (환율 고정이라 250*1400)
    item = await _item(db, item_id)
    assert item.currency == "USD"
    assert item.avg_price_ccy == Decimal("250.0000")
    assert item.avg_price == Decimal("350000.00")


async def test_달러_매도의_실현손익이_달러로도_박제된다(db, ctx, fx):
    # given: $200 10주 매수
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")
    await _buy(db, ctx, item_id, qty="10", price="200", tx_date=date(2026, 1, 1))

    # when: $300 에 5주 매도
    await service.sell(
        db, ctx.household, item_id,
        PortfolioSellRequest(
            quantity=Decimal("5"), sellPrice=Decimal("300"), txDate=date(2026, 2, 1),
        ),
    )

    # then: 달러 손익 (300-200)*5 = 500
    sells = [t for t in await _txs(db, item_id) if t.pt_type == "SELL"]
    assert sells[0].realized_pnl_ccy == Decimal("500.00")
    assert sells[0].realized_cost_basis_ccy == Decimal("1000.00")


async def test_원화로만_기록된_과거_거래가_섞이면_달러_평단은_비운다(db, ctx, fx):
    """없는 값을 지어내지 않는다 — price_ccy 가 없는 거래가 하나라도 있으면
    달러 평단을 계산할 근거가 없다."""
    # given: 레거시 매수 1건(원화만) + 신규 달러 매수 1건
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")
    await _buy(db, ctx, item_id, qty="10", price="200", tx_date=date(2026, 2, 1))

    legacy = (await _txs(db, item_id))[0]
    legacy.price_ccy = None      # 마이그레이션 이전 데이터 재현
    legacy.fx_rate = Decimal("1.0000")
    await db.flush()
    await service.recalc_item(db, ctx.household, item_id)

    # then: 원화 평단은 살아있고 달러 평단은 NULL
    item = await _item(db, item_id)
    assert item.avg_price > 0
    assert item.avg_price_ccy is None


# =========================================================
# 6~7. 통화 도출 / 합산 불변
# =========================================================


@pytest.mark.parametrize(
    "market,expected",
    [
        (Market.NASDAQ, "USD"),
        (Market.NYSE, "USD"),
        (Market.KRX_KOSPI, "KRW"),
        (Market.KRX_KOSDAQ, "KRW"),
        (Market.OTHER, "KRW"),
    ],
)
async def test_통화는_시장에서_도출된다(db, ctx, fx, market, expected):
    """item 과 tx 가 각자 통화를 들면 갈릴 수 있다 — market 하나에서 도출한다."""
    item_id = await _new_item(db, ctx, market=market, code="X")
    item = await _item(db, item_id)
    assert item.currency == expected


async def test_순자산_합산은_원화_컬럼만_쓴다(db, ctx, fx):
    """USD 도입 후에도 계좌 평가액은 KRW 기준이어야 한다."""
    # given: 달러 종목 10주 @$250 (= 350,000원), 현재가도 동일
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL", price="350000")
    await _buy(db, ctx, item_id, qty="10", price="250", tx_date=date(2026, 3, 1))

    # when
    overview = await service.get_account_overview(db, ctx.household, ctx.account.id)

    # then: 평가액 = 10 * 350,000 원 (달러 숫자 2,500 이 아니라)
    assert overview.account.portfolio_valuation == Decimal("3500000.00")
