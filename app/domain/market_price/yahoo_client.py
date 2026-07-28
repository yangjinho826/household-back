import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_RETRY_BACKOFF_SEC = 1.0
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ChartQuote:
    """Yahoo chart endpoint 의 meta 에서 뽑은 시세 + 이름.

    name 은 meta 에 longName/shortName 없으면 None — 호출자가 fallback 결정.
    """

    price: Decimal
    name: str | None


def _is_retryable(error: httpx.HTTPError) -> bool:
    """일시 오류만 재시도 — 영구 오류(404 등) 는 즉시 None"""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in _RETRYABLE_STATUS
    return isinstance(error, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError))


async def _request_chart(symbol: str, params: dict) -> dict | None:
    """Yahoo chart endpoint 1회 호출 → JSON payload. 일시 오류 1회 재시도.

    시세(1d)든 월봉(1mo)이든 같은 endpoint — params 만 다르다. 파싱은 호출자 책임.
    """
    url = f"{_BASE_URL}/{symbol}"
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            if attempt == 0 and _is_retryable(e):
                logger.info(
                    "Yahoo 일시 오류 (symbol=%s, %s) — %.1fs 후 재시도",
                    symbol, type(e).__name__, _RETRY_BACKOFF_SEC,
                )
                await asyncio.sleep(_RETRY_BACKOFF_SEC)
                continue
            logger.warning("Yahoo HTTP 실패 (symbol=%s): %s", symbol, e)
            return None
    return None


async def fetch_chart_quote(symbol: str) -> ChartQuote | None:
    """Yahoo Finance chart endpoint 로 현재가 + 이름(있으면).

    영구 오류 / 가격 누락 → None. 호출자는 None 받으면 skip / 다음 후보 시도.
    """
    payload = await _request_chart(symbol, {"interval": "1d", "range": "1d"})
    if payload is None:
        return None

    chart = payload.get("chart") or {}
    if chart.get("error"):
        logger.warning("Yahoo chart.error (symbol=%s): %s", symbol, chart["error"])
        return None

    results = chart.get("result") or []
    if not results:
        logger.warning("Yahoo result 비어있음 (symbol=%s)", symbol)
        return None

    meta = results[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        logger.warning("Yahoo regularMarketPrice 누락 (symbol=%s)", symbol)
        return None

    name = meta.get("longName") or meta.get("shortName")
    return ChartQuote(price=Decimal(str(price)), name=name)


async def fetch_monthly_closes(
    symbol: str, range_: str = "2y",
) -> dict[date, Decimal] | None:
    """월봉 종가 시계열 → {월1일: 종가}. interval=1mo.

    자산 스냅샷 backfill 용 — 종목당 1회 호출로 range_ 기간 월별 종가를 확보한다.
    close 가 null 인 달(휴장/미상장)은 제외. 실패 / 데이터 없음 → None(호출자 skip).
    timestamp 는 UTC 로 보고 그 달 1일로 정규화(snapshot price_date 컨벤션).
    """
    payload = await _request_chart(symbol, {"interval": "1mo", "range": range_})
    if payload is None:
        return None

    chart = payload.get("chart") or {}
    if chart.get("error"):
        logger.warning("Yahoo chart.error (symbol=%s): %s", symbol, chart["error"])
        return None

    results = chart.get("result") or []
    if not results:
        return None

    result0 = results[0]
    timestamps = result0.get("timestamp") or []
    quotes = (result0.get("indicators") or {}).get("quote") or [{}]
    closes = quotes[0].get("close") or []

    out: dict[date, Decimal] = {}
    for ts, close in zip(timestamps, closes, strict=False):
        if close is None:
            continue
        month = datetime.fromtimestamp(ts, tz=UTC).date().replace(day=1)
        out[month] = Decimal(str(close))
    return out or None
