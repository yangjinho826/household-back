"""portfolio_items.current_price 자동 갱신 서비스.

스케줄 잡(KR 16:10 / US 09:10) 이 같은 refresh() 호출 — markets 만 다름.
USD 시장(NASDAQ/NYSE) 은 시세 갱신 시점에 currency_rates(USD/KRW) 환율 적용해 KRW 박제 —
sum_valuation_by_account 의 qty * current_price SUM 이 단일 통화에서만 의미 있어서.

야후 심볼은 Market enum 의 yahoo_suffix 로 1:1 매핑 — fallback 없음, 항상 1번 호출.
"""
import asyncio
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exchange_rate.enum import CurrencyCode
from app.domain.exchange_rate.repository import CurrencyRateRepository
from app.domain.market_price.yahoo_client import fetch_chart_quote
from app.domain.portfolio.enum import Market
from app.domain.portfolio.repository import PortfolioItemRepository
from app.domain.portfolio.yahoo import build_yahoo_symbol

logger = logging.getLogger(__name__)

# USD 시장 — KRW 환산 분기용
_USD_MARKETS = frozenset({Market.NASDAQ, Market.NYSE})

# 청크 병렬화 — Yahoo rate-limit 회피 + 종목 N개 확장성
_CHUNK_SIZE = 10
_CHUNK_SLEEP_SEC = 0.2


@dataclass
class RefreshResult:
    fetched: int        # Yahoo 응답 받은 종목 수
    skipped: int        # fetch 실패 종목 수
    updated_rows: int   # DB row 업데이트 수


def _chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def _fetch_one(
    code: str, market: Market, fx_rate: Decimal | None,
) -> Decimal | None:
    """시장별 1:1 야후 심볼로 1번 호출. USD 시장이면 fx_rate 곱해 KRW 환산."""
    symbol = build_yahoo_symbol(market, code)
    quote = await fetch_chart_quote(symbol)
    if quote is None or quote.price <= 0:
        return None
    price = quote.price
    if market in _USD_MARKETS and fx_rate is not None:
        price = price * fx_rate
    return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def refresh(session: AsyncSession, markets: list[Market]) -> RefreshResult:
    """주어진 시장들의 모든 활성 portfolio_items.current_price 자동 갱신.

    1. USD 시장이 포함되면 최신 환율 fetch — 없으면 USD 시장 제외
    2. (code, market) DISTINCT 추출 — 가계부 N개여도 야후 호출은 종목 수만큼
    3. 청크 병렬 (_CHUNK_SIZE 개씩 asyncio.gather), 청크 사이 sleep
    4. 가격 캐시 모은 후 bulk update
    5. fetch 실패는 per-item skip + 로그 (yahoo_client 내부 retry 1회)
    """
    if not markets:
        return RefreshResult(0, 0, 0)

    needs_fx = any(m in _USD_MARKETS for m in markets)
    fx_rate: Decimal | None = None
    if needs_fx:
        latest = await CurrencyRateRepository(session).find_by_pair(
            CurrencyCode.USD, CurrencyCode.KRW,
        )
        if latest is None:
            logger.error(
                "환율 없음 — USD 시장 종목 갱신 skip. 환율 잡 먼저 실행 필요"
            )
            markets = [m for m in markets if m not in _USD_MARKETS]
            if not markets:
                return RefreshResult(0, 0, 0)
        else:
            fx_rate = latest.rate
            logger.info("USD 환산 환율 적용 (%s)", fx_rate)

    repo = PortfolioItemRepository(session)
    pairs = await repo.find_active_distinct_code_market_by_markets(markets)

    prices_to_apply: dict[tuple[str, Market], Decimal] = {}
    fetched = 0
    skipped = 0
    chunk_list = list(_chunks(pairs, _CHUNK_SIZE))
    last_idx = len(chunk_list) - 1

    for idx, chunk in enumerate(chunk_list):
        results = await asyncio.gather(
            *[_fetch_one(code, market, fx_rate) for code, market in chunk],
            return_exceptions=True,
        )
        for (code, market), price_or_exc in zip(chunk, results, strict=True):
            if isinstance(price_or_exc, Exception):
                logger.warning(
                    "fetch 예외 (code=%s, market=%s): %s",
                    code, market, price_or_exc,
                )
                skipped += 1
                continue
            if price_or_exc is None:
                skipped += 1
                continue
            prices_to_apply[(code, market)] = price_or_exc
            fetched += 1

        if idx < last_idx:
            await asyncio.sleep(_CHUNK_SLEEP_SEC)

    updated_rows = await repo.bulk_update_current_price_by_code_market(prices_to_apply)

    logger.info(
        "시세 갱신 (markets=%s, fetched=%d, skipped=%d, rows=%d)",
        [m.value for m in markets], fetched, skipped, updated_rows,
    )
    return RefreshResult(fetched=fetched, skipped=skipped, updated_rows=updated_rows)
