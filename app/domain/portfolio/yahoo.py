"""야후 파이낸스 어댑터 — 종목 조회 (이름 + 현재가).

- KR 은 KOSPI(.KS) → KOSDAQ(.KQ) 순서로 fallback.
- US 는 접미사 없이 ticker 그대로.
- 모든 호출은 `market_price.yahoo_client.fetch_chart_quote` (httpx) 로 단일화.
"""

import logging
from decimal import Decimal

from app.core.exceptions import CustomException, ErrorCode
from app.domain.market_price.yahoo_client import fetch_chart_quote
from app.domain.portfolio.enum import Country

logger = logging.getLogger(__name__)


def build_yahoo_symbols(country: Country, code: str) -> list[str]:
    """국가/코드를 야후 심볼 후보 목록으로 변환."""
    code = code.strip()
    if country == Country.KR:
        return [f"{code}.KS", f"{code}.KQ"]
    return [code]


async def lookup(country: Country, code: str) -> tuple[str, Decimal, str]:
    """(종목명, 현재가, 사용된 야후 심볼) 반환. 모든 후보 실패 시 CustomException."""
    for symbol in build_yahoo_symbols(country, code):
        quote = await fetch_chart_quote(symbol)
        if quote is not None and quote.price > 0:
            return quote.name or code, quote.price, symbol

    logger.info("야후 종목 조회 실패 (country=%s, code=%s)", country, code)
    raise CustomException(ErrorCode.STOCK_LOOKUP_FAILED)
