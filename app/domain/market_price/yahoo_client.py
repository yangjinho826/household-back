import asyncio
import logging
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


def _is_retryable(error: httpx.HTTPError) -> bool:
    """일시 오류만 재시도 — 영구 오류(404 등) 는 즉시 None"""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in _RETRYABLE_STATUS
    # ConnectTimeout / ReadTimeout / ConnectError / PoolTimeout 등 네트워크 일시 오류
    return isinstance(error, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError))


async def fetch_chart_close_price(symbol: str) -> Decimal | None:
    """Yahoo Finance chart endpoint 에서 regularMarketPrice 만 뽑아 반환.

    시세든 환율(KRW=X) 이든 같은 endpoint 라 단일 책임.
    일시 오류(429/5xx/timeout) 는 1회 재시도. 영구 오류 / 누락 → None.
    호출자는 None 받으면 skip.
    """
    url = f"{_BASE_URL}/{symbol}"
    params = {"interval": "1d", "range": "1d"}

    for attempt in range(2):  # 최대 2회 (원래 1회 + retry 1회)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
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

        return Decimal(str(price))

    return None
