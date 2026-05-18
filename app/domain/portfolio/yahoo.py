"""야후 파이낸스 어댑터 — 종목 조회 (이름 + 현재가).

Market enum 의 yahoo_suffix 로 1:1 야후 심볼 생성. fallback 없음.
모든 호출은 market_price.yahoo_client (httpx) 단일 패턴.
"""

import logging
from decimal import Decimal

from app.core.exceptions import CustomException, ErrorCode
from app.domain.market_price.yahoo_client import fetch_chart_quote
from app.domain.portfolio.enum import Market

logger = logging.getLogger(__name__)


def build_yahoo_symbol(market: Market, code: str) -> str:
    """시장별 1:1 야후 심볼 — fallback 없음."""
    code = code.strip()
    suffix = market.yahoo_suffix
    return f"{code}{suffix}" if suffix else code


async def lookup(market: Market, code: str) -> tuple[str, Decimal, str]:
    """(종목명, 현재가, 사용된 야후 심볼) 반환. 실패 시 CustomException."""
    symbol = build_yahoo_symbol(market, code)
    quote = await fetch_chart_quote(symbol)
    if quote is not None and quote.price > 0:
        return quote.name or code, quote.price, symbol

    logger.info("야후 종목 조회 실패 (market=%s, code=%s)", market, code)
    raise CustomException(ErrorCode.STOCK_LOOKUP_FAILED)
