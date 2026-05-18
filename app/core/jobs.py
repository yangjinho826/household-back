"""스케줄 잡 함수 모음 — scheduler 와 독립 (수동 import 호출 가능).

각 잡은 `run_locked_job` 으로 감싸 — 자체 세션 + advisory lock + 트랜잭션.
"""
from app.core.scheduler import run_locked_job
from app.domain.exchange_rate import service as exchange_rate_service


async def refresh_usd_krw_job() -> None:
    """USD/KRW 환율 갱신 — 매일 09:00 KST."""
    await run_locked_job("refresh_usd_krw", exchange_rate_service.refresh)
