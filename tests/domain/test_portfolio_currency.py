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
| 8 | 매매손익 행이 거래통화 손익·수익률을 함께 내려준다 |
| 9 | 레거시 매도는 매매손익 행의 ccy 값이 NULL |
| 10 | 매매손익 요약은 통화가 섞이므로 KRW 단독 |
| 11 | 거래 수정도 달러 입력을 환산한다 (매수와 같은 단위 계약) |
| 12 | 레거시 거래 수정은 원화 입력 그대로 (없는 달러가를 만들지 않는다) |
| 13 | 거래통화 필드가 JSON 숫자로 나간다 (문자열이면 프론트 숫자 연산이 터진다) |
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
    PortfolioTxUpdateRequest,
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


# =========================================================
# 8~10. 매매손익 카드의 거래통화 기준
# =========================================================


async def _sell(db, ctx, item_id, *, qty: str, price: str, tx_date: date, fee: str = "0"):
    return await service.sell(
        db, ctx.household, item_id,
        PortfolioSellRequest(
            quantity=Decimal(qty), sellPrice=Decimal(price),
            txDate=tx_date, fee=Decimal(fee),
        ),
    )


async def test_매매손익_행이_거래통화_손익과_수익률을_함께_내려준다(db, ctx, fx):
    """원화 손익률에는 환차손익이 섞인다 — 종목 자체 성과는 달러로 봐야 한다."""
    # given: $200 10주 매수 → $300 5주 매도 (수수료 $1)
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")
    await _buy(db, ctx, item_id, qty="10", price="200", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, item_id, qty="5", price="300", tx_date=date(2026, 2, 1), fee="1")

    # when
    res = await service.get_realized_pnl_by_item(db, ctx.household, item_id)

    # then: 달러 트랙 — 손익 (300-200)*5 - 1 = 499, 원가 1,000 → 49.90%
    row = res.rows[0]
    assert row.currency == "USD"
    assert row.sell_price_ccy == Decimal("300.0000")
    assert row.amount_ccy == Decimal("1500.00")
    assert row.fee_ccy == Decimal("1.00")
    assert row.settlement_ccy == Decimal("1499.00")
    assert row.realized_pnl_ccy == Decimal("499.00")
    assert row.realized_rate_ccy == Decimal("49.90")


async def test_레거시_매도는_매매손익_행의_거래통화_값이_비어있다(db, ctx, fx):
    """원본 달러가가 없는 과거 매도는 달러 손익을 지어내지 않는다."""
    # given: 매수/매도 후 매수 거래를 레거시(price_ccy=NULL)로 되돌려 재계산
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")
    await _buy(db, ctx, item_id, qty="10", price="200", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, item_id, qty="5", price="300", tx_date=date(2026, 2, 1))

    legacy = [t for t in await _txs(db, item_id) if t.pt_type == "BUY"][0]
    legacy.price_ccy = None
    legacy.fx_rate = Decimal("1.0000")
    await db.flush()
    await service.recalc_item(db, ctx.household, item_id)

    # when
    res = await service.get_realized_pnl_by_item(db, ctx.household, item_id)

    # then: 원화 손익은 살아있고 달러 값만 비어야 한다
    row = res.rows[0]
    assert row.realized_pnl != 0
    assert row.realized_pnl_ccy is None
    assert row.realized_rate_ccy is None


async def test_매매손익_요약은_원화_단독이다(db, ctx, fx):
    """계좌 단위는 원화 종목과 달러 종목의 매도가 한 표에 섞인다 —
    통화가 다른 금액을 더할 수 없으므로 요약은 KRW 기준 하나만 둔다."""
    # given: 달러 종목 매도 + 원화 종목 매도
    usd_item = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")
    await _buy(db, ctx, usd_item, qty="10", price="200", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, usd_item, qty="5", price="300", tx_date=date(2026, 2, 1))

    krw_item = await _new_item(db, ctx, market=Market.KRX_KOSPI, code="005930")
    await _buy(db, ctx, krw_item, qty="10", price="70000", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, krw_item, qty="5", price="80000", tx_date=date(2026, 2, 1))

    # when
    res = await service.get_realized_pnl_by_account(db, ctx.household, ctx.account.id)

    # then: 요약에는 ccy 필드가 아예 없다 (합산 불가를 스키마로 못박음)
    assert not hasattr(res.summary, "total_realized_ccy")
    # 원화 합계 = 달러 매도 (300-200)*5*1400 = 700,000 + 원화 (80000-70000)*5 = 50,000
    assert res.summary.total_realized == Decimal("750000.00")


# =========================================================
# 11~12. 거래 수정의 입력 단위
# =========================================================


async def test_달러_거래_수정도_달러_입력을_환산한다(db, ctx, fx):
    """매수는 달러로 받는데 수정만 원화로 받으면, 화면에 표시된 달러 단가를
    그대로 되돌려보내는 순간 원화 평단이 환율만큼 찌그러진다."""
    # given: $200 10주 매수
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")
    await _buy(db, ctx, item_id, qty="10", price="200", tx_date=date(2026, 1, 1))
    tx = (await _txs(db, item_id))[0]

    # when: 단가를 $250, 수수료를 $2 로 수정
    await service.update_portfolio_transaction(
        db, ctx.household, tx.id,
        PortfolioTxUpdateRequest(price=Decimal("250"), fee=Decimal("2")),
    )

    # then: 달러 원본은 입력 그대로, 원화는 박제 환율로 파생
    tx = (await _txs(db, item_id))[0]
    assert tx.price_ccy == Decimal("250.0000")
    assert tx.fee_ccy == Decimal("2.00")
    assert tx.price == Decimal("350000.00")   # 250 × 1,400
    assert tx.fee == Decimal("2800.00")

    item = await _item(db, item_id)
    assert item.avg_price_ccy == Decimal("250.2000")   # (250*10 + 2) / 10
    assert item.avg_price == Decimal("350280.00")


async def test_레거시_거래_수정은_원화_입력을_그대로_쓴다(db, ctx, fx):
    """원본 달러가가 없는 거래는 화면도 원화로 편집한다 — 달러 입력으로 오해해
    환율을 곱하면 1,400배가 된다."""
    # given: price_ccy 가 없는 과거 거래
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")
    await _buy(db, ctx, item_id, qty="10", price="200", tx_date=date(2026, 1, 1))
    legacy = (await _txs(db, item_id))[0]
    legacy.price_ccy = None
    legacy.fee_ccy = None
    await db.flush()

    # when: 원화 단가 300,000 으로 수정
    await service.update_portfolio_transaction(
        db, ctx.household, legacy.id,
        PortfolioTxUpdateRequest(price=Decimal("300000")),
    )

    # then: 원화 그대로. 달러 원본은 여전히 비어있다
    tx = (await _txs(db, item_id))[0]
    assert tx.price == Decimal("300000.00")
    assert tx.price_ccy is None


# =========================================================
# 13. 직렬화
# =========================================================


async def test_거래통화_필드는_JSON_숫자로_나간다(db, ctx, fx):
    """Decimal 은 직렬화 타입을 안 붙이면 JSON 문자열이 된다. 프론트가
    `rate.toFixed()` 처럼 숫자로 다루므로 문자열이 새면 화면이 통째로 죽는다."""
    # given: 달러 매수·매도 1건씩
    item_id = await _new_item(db, ctx, market=Market.NASDAQ, code="AAPL")
    await _buy(db, ctx, item_id, qty="10", price="200", tx_date=date(2026, 1, 1))
    await _sell(db, ctx, item_id, qty="5", price="300", tx_date=date(2026, 2, 1), fee="1")

    # when: 화면이 쓰는 3개 응답을 그대로 직렬화
    item = (await service.get_portfolio_detail(db, ctx.household, item_id)).model_dump(
        mode="json", by_alias=True,
    )
    row = (
        await service.get_realized_pnl_by_item(db, ctx.household, item_id)
    ).rows[0].model_dump(mode="json", by_alias=True)

    # then: 어느 필드도 문자열이 아니어야 한다
    for key in ("avgPriceCcy", "currentPriceCcy", "profitLossCcy", "profitLossRateCcy"):
        assert isinstance(item[key], (int, float)), f"{key}={item[key]!r}"
    for key in (
        "sellPriceCcy", "amountCcy", "feeCcy",
        "settlementCcy", "realizedPnlCcy", "realizedRateCcy",
    ):
        assert isinstance(row[key], (int, float)), f"{key}={row[key]!r}"
