import logging
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.exchange_rate.model import ExchangeRate
from app.domain.exchange_rate.repository import ExchangeRateRepository
from app.domain.market_price.yahoo_client import fetch_chart_close_price

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

USD = "USD"
KRW = "KRW"
USD_KRW_SYMBOL = "KRW=X"


async def refresh(session: AsyncSession) -> None:
    """USD/KRW 환율 fetch → 오늘 날짜 row 저장 (같은 날짜면 갱신).

    실패 시 ERROR 로그만 — 잡 전체 실패 막지 않음 (다음 잡 진행).
    """
    today = datetime.now(KST).date()
    repo = ExchangeRateRepository(session)

    price = await fetch_chart_close_price(USD_KRW_SYMBOL)
    if price is None:
        logger.error("환율 fetch 실패 (symbol=%s) — skip", USD_KRW_SYMBOL)
        return

    rate = price.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    existing = await repo.find_by_date(today, USD, KRW)
    if existing:
        existing.rate = rate
        await session.flush()
        logger.info("환율 갱신 (date=%s, USD→KRW=%s)", today, rate)
        return

    await repo.save(
        ExchangeRate(
            snapshot_date=today,
            base_currency=USD,
            quote_currency=KRW,
            rate=rate,
            data_stat_cd=DataStatus.ACTIVE,
        )
    )
    logger.info("환율 박제 (date=%s, USD→KRW=%s)", today, rate)
