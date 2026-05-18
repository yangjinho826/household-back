import logging
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.exchange_rate.enum import CurrencyCode
from app.domain.exchange_rate.model import CurrencyRate
from app.domain.exchange_rate.repository import CurrencyRateRepository
from app.domain.market_price.yahoo_client import fetch_chart_quote

logger = logging.getLogger(__name__)

# Yahoo 표기: USD 가 base 면 `{quote}=X` 단축 표기 → KRW=X 는 1 USD = ? KRW
USD_KRW_SYMBOL = "KRW=X"


async def refresh(session: AsyncSession) -> None:
    """USD/KRW 환율 fetch → (base, quote) row 가 있으면 update, 없으면 insert.

    fetch 실패 시 ERROR 로그만 — 잡 전체 실패 X (다음 스케줄에 재시도).
    """
    quote = await fetch_chart_quote(USD_KRW_SYMBOL)
    if quote is None:
        logger.error("환율 fetch 실패 (symbol=%s) — skip", USD_KRW_SYMBOL)
        return

    rate = quote.price.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    repo = CurrencyRateRepository(session)
    existing = await repo.find_by_pair(CurrencyCode.USD, CurrencyCode.KRW)

    if existing:
        existing.rate = rate                  # dirty checking → flush 시 UPDATE
        await session.flush()                 # last_mdfcn_dt 는 onupdate 로 자동 갱신
        logger.info("환율 갱신 (USD→KRW=%s)", rate)
        return

    await repo.save(
        CurrencyRate(
            base_currency=CurrencyCode.USD,
            quote_currency=CurrencyCode.KRW,
            rate=rate,
            data_stat_cd=DataStatus.ACTIVE,
        )
    )
    logger.info("환율 박제 (USD→KRW=%s)", rate)
