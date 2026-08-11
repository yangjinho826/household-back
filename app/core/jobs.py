"""스케줄 잡 함수 모음 — scheduler 와 독립 (수동 import 호출 가능).

각 잡은 `run_locked_job` 으로 감싸 — 자체 세션 + advisory lock + 트랜잭션.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.demo import seed as demo_seed
from app.core.idempotency import service as idempotency_service
from app.core.scheduler import run_locked_job
from app.domain.account_snapshot import service as account_snapshot_service
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


async def cleanup_idempotency_job() -> None:
    """idempotency 레코드 만료 정리 — 매시간."""
    await run_locked_job("cleanup_idempotency", idempotency_service.cleanup_expired)


async def create_monthly_snapshots_job() -> None:
    """월간 자산 스냅샷 자동 박제 — 매월 1일 00:30 KST (지난달 마감).

    전월 말일 종가가 이미 시세에 반영된 시점. 모든 가계부 순회, 이미 박제됐으면 skip.
    """

    async def _run(session: AsyncSession) -> None:
        await account_snapshot_service.create_monthly_snapshots_for_all(session)

    await run_locked_job("create_monthly_snapshots", _run)


async def reset_demo_job() -> None:
    """데모 가계부 리셋 — 매일 05:00 KST (백업 03:00 · 복구 리허설 04:00 다음).

    이력서에 공개된 체험 계정이라 누가 데이터를 고치거나 지워도 하루 안에 원복된다.
    """
    if not settings.DEMO_SEED_ENABLED:
        return
    await run_locked_job("reset_demo", demo_seed.seed_demo)
