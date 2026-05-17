"""야후 파이낸스 어댑터 — 종목 조회 (이름 + 현재가).

- KR 은 KOSPI(.KS) → KOSDAQ(.KQ) 순서로 fallback.
- US 는 접미사 없이 ticker 그대로.
- yfinance.Ticker.fast_info 우선, 실패 시 .info fallback (info 는 5초 이상 걸릴 수 있음).
"""

import asyncio
import logging
from decimal import Decimal

import yfinance as yf

from app.core.exceptions import CustomException, ErrorCode
from app.domain.portfolio.enum import Country

logger = logging.getLogger(__name__)


def build_yahoo_symbols(country: Country, code: str) -> list[str]:
    """국가/코드를 야후 심볼 후보 목록으로 변환."""
    code = code.strip()
    if country == Country.KR:
        return [f"{code}.KS", f"{code}.KQ"]
    return [code]


def _fetch_quote(symbol: str) -> tuple[str | None, Decimal | None]:
    """단일 심볼에 대해 (이름, 현재가) 반환. 실패 시 (None, None)."""
    try:
        ticker = yf.Ticker(symbol)
    except Exception as exc:
        logger.warning("yfinance Ticker init 실패 (symbol=%s): %s", symbol, exc)
        return None, None

    price: Decimal | None = None
    try:
        last_price = ticker.fast_info.get("lastPrice")
        if last_price:
            price = Decimal(str(last_price))
    except Exception:
        price = None

    name: str | None = None
    if price is not None:
        try:
            info = ticker.info or {}
            name = info.get("longName") or info.get("shortName")
        except Exception:
            name = None

    return name, price


async def lookup(country: Country, code: str) -> tuple[str, Decimal, str]:
    """(종목명, 현재가, 사용된 야후 심볼) 반환. 모든 후보 실패 시 CustomException."""
    for symbol in build_yahoo_symbols(country, code):
        name, price = await asyncio.to_thread(_fetch_quote, symbol)
        if price is not None and price > 0:
            return name or code, price, symbol

    logger.info("야후 종목 조회 실패 (country=%s, code=%s)", country, code)
    raise CustomException(ErrorCode.STOCK_LOOKUP_FAILED)
