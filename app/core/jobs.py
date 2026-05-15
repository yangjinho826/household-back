"""스케줄 잡 함수 모음 — scheduler 와 독립 (수동 import 호출 가능).

각 잡은 `run_locked_job` 으로 감싸 — 자체 세션 + advisory lock + 트랜잭션.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scheduler import run_locked_job
from app.domain.exchange_rate import service as exchange_rate_service
from app.domain.market_price import service as market_price_service
from app.domain.portfolio.enum import Market


async def refresh_usd_krw_job() -> None:
    """USD/KRW 환율 갱신 — 매일 09:00 KST."""
    await run_locked_job("refresh_usd_krw", exchange_rate_service.refresh)


async def refresh_kr_prices_job() -> None:
    """국장 시세 갱신 — 매일 16:10 KST (국장 close 직후)."""

    async def _run(session: AsyncSession) -> None:
        await market_price_service.refresh(
            session, [Market.KRX_KOSPI, Market.KRX_KOSDAQ],
        )

    await run_locked_job("refresh_kr_prices", _run)


async def refresh_us_prices_job() -> None:
    """미장 시세 갱신 — 매일 09:10 KST (미장 close + 환율 갱신 후)."""

    async def _run(session: AsyncSession) -> None:
        await market_price_service.refresh(
            session, [Market.NASDAQ, Market.NYSE],
        )

    await run_locked_job("refresh_us_prices", _run)
