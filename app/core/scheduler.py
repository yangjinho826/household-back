import logging
from collections.abc import Awaitable, Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

scheduler = AsyncIOScheduler(timezone=KST)


async def try_advisory_lock(session: AsyncSession, key: str) -> bool:
    """PostgreSQL transaction-scoped advisory lock 시도.

    트랜잭션 종료 시 자동 해제. 실패 시 False — 호출자가 skip 결정.
    같은 잡이 다중 인스턴스/워커에서 동시 진입해도 1개만 통과.
    """
    result = await session.execute(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
        {"key": key},
    )
    return bool(result.scalar())


async def run_locked_job(
    job_name: str, fn: Callable[[AsyncSession], Awaitable[None]],
) -> None:
    """잡 공통 보일러플레이트:
    1. 자체 세션 생성 (request-scoped DI 와 분리)
    2. 명시 트랜잭션 시작 (advisory_xact_lock 가 살아있을 범위 보장)
    3. advisory lock 시도 — 실패 시 조용히 skip
    4. 실제 작업 실행
    5. 예외는 로그 + 재발생 (스케줄러가 다음 trigger 대기)
    """
    async with async_session() as session:
        async with session.begin():
            if not await try_advisory_lock(session, job_name):
                logger.info("%s skipped (lock not acquired)", job_name)
                return
            try:
                await fn(session)
                logger.info("%s 완료", job_name)
            except Exception:
                logger.exception("%s 실패", job_name)
                raise


def register_jobs() -> None:
    """모든 잡을 단일 scheduler 인스턴스에 등록.

    스케줄:
    - 환율 09:00 KST (월~금) → 미장 종목 갱신 09:10 (화~토) 직전 보장
    - 미장 09:10 KST (화~토) → KST 06:00 미장 close 후 환율 갱신 직후
    - 국장 16:10 KST (월~금) → 국장 close 직후
    """
    # import 는 함수 내부에서 — 순환 의존 회피 (jobs 가 scheduler 모듈 의존)
    from app.core import jobs

    scheduler.add_job(
        jobs.refresh_usd_krw_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=KST),
        id="refresh_usd_krw",
        replace_existing=True,
    )
    scheduler.add_job(
        jobs.refresh_us_prices_job,
        CronTrigger(day_of_week="tue-sat", hour=9, minute=10, timezone=KST),
        id="refresh_us_prices",
        replace_existing=True,
    )
    scheduler.add_job(
        jobs.refresh_kr_prices_job,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=10, timezone=KST),
        id="refresh_kr_prices",
        replace_existing=True,
    )
    logger.info("스케줄 잡 등록 완료 (3개)")
