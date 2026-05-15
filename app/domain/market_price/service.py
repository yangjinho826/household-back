import asyncio
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exchange_rate.repository import ExchangeRateRepository
from app.domain.market_price.yahoo_client import fetch_chart_close_price
from app.domain.portfolio.enum import Market
from app.domain.portfolio.repository import PortfolioItemRepository

logger = logging.getLogger(__name__)

_USD_MARKETS = frozenset({Market.NASDAQ, Market.NYSE})

# 시장 → Yahoo ticker 접미사 매핑
_MARKET_SUFFIX: dict[Market, str] = {
    Market.KRX_KOSPI: ".KS",
    Market.KRX_KOSDAQ: ".KQ",
    Market.NASDAQ: "",
    Market.NYSE: "",
}

# 청크 병렬화 — Yahoo rate-limit 회피 + 종목 N개 확장성
_CHUNK_SIZE = 10
_CHUNK_SLEEP_SEC = 0.2


@dataclass
class RefreshResult:
    fetched: int        # Yahoo 응답 받은 ticker 수
    skipped: int        # fetch 실패 ticker 수
    updated_rows: int   # DB row 업데이트 수


def _to_yahoo_symbol(ticker: str, market: Market) -> str:
    suffix = _MARKET_SUFFIX[market]
    return f"{ticker}{suffix}" if suffix else ticker


def _chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def _fetch_one(
    ticker: str, market: Market, fx_rate: Decimal | None,
) -> Decimal | None:
    """단일 종목 fetch → KRW 환산까지. gather 단위.

    USD 시장이면 × fx_rate 환산. 그 외는 그대로 quantize.
    """
    symbol = _to_yahoo_symbol(ticker, market)
    raw = await fetch_chart_close_price(symbol)
    if raw is None:
        return None

    if market in _USD_MARKETS and fx_rate is not None:
        return (raw * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def refresh(session: AsyncSession, markets: list[Market]) -> RefreshResult:
    """주어진 시장들의 모든 활성 종목 current_price 자동 갱신.

    국장 잡과 미장 잡이 같은 함수 호출, 시장만 다름.
    1. USD 시장이 포함되면 최신 환율 fetch (없으면 USD 시장 종목 skip)
    2. (ticker, market) DISTINCT 추출 — 가계부 N개여도 Yahoo 호출 ticker 수만큼
    3. 청크 병렬 (_CHUNK_SIZE 개씩 asyncio.gather)
       - 청크 사이 _CHUNK_SLEEP_SEC sleep — Yahoo rate-limit 회피
       - 마지막 청크 뒤엔 sleep X
    4. 가격 캐시 모은 후 bulk update — 매치 row 모두 일괄
    5. fetch 실패 종목은 per-item skip + 로그 (yahoo_client 안에서 retry 1회)
    """
    if not markets:
        return RefreshResult(0, 0, 0)

    needs_fx = any(m in _USD_MARKETS for m in markets)
    fx_rate: Decimal | None = None
    if needs_fx:
        latest = await ExchangeRateRepository(session).find_latest("USD", "KRW")
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

    portfolio_repo = PortfolioItemRepository(session)
    pairs = await portfolio_repo.find_active_distinct_ticker_market_by_markets(markets)

    prices_to_apply: dict[tuple[str, Market], Decimal] = {}
    fetched = 0
    skipped = 0
    chunk_list = list(_chunks(pairs, _CHUNK_SIZE))
    last_idx = len(chunk_list) - 1

    for idx, chunk in enumerate(chunk_list):
        results = await asyncio.gather(
            *[_fetch_one(t, m, fx_rate) for t, m in chunk],
            return_exceptions=True,
        )
        for (ticker, market), price_or_exc in zip(chunk, results, strict=True):
            if isinstance(price_or_exc, Exception):
                logger.warning(
                    "fetch 예외 (ticker=%s, market=%s): %s",
                    ticker, market, price_or_exc,
                )
                skipped += 1
                continue
            if price_or_exc is None:
                skipped += 1
                continue
            prices_to_apply[(ticker, market)] = price_or_exc
            fetched += 1

        # 마지막 청크 뒤엔 sleep 없음 (불필요한 지연 제거)
        if idx < last_idx:
            await asyncio.sleep(_CHUNK_SLEEP_SEC)

    updated_rows = await portfolio_repo.bulk_update_current_price_by_ticker_market(
        prices_to_apply,
    )

    logger.info(
        "시세 갱신 (markets=%s, fetched=%d, skipped=%d, rows=%d)",
        [m.value for m in markets], fetched, skipped, updated_rows,
    )
    return RefreshResult(fetched=fetched, skipped=skipped, updated_rows=updated_rows)
