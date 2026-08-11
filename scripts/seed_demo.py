"""데모 가계부 수동 시딩 — 새 환경 구축·데모가 깨졌을 때 즉시 복구용.

    docker compose exec -T household-back python -m scripts.seed_demo

DEMO_SEED_ENABLED 와 무관하게 항상 동작한다 — 사람이 명시적으로 부른 것이라
자동 실행 게이트(테스트 오염 방지용)를 적용할 이유가 없다.

스케줄 잡과 같은 run_locked_job 을 타므로 05:00 리셋과 겹쳐도 하나만 통과한다.
"""
import asyncio
import logging

from app.core.demo import seed as demo_seed
from app.core.logging import setup_logging
from app.core.scheduler import run_locked_job

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    await run_locked_job("reset_demo", demo_seed.seed_demo)
    logger.info("수동 데모 시딩 종료")


if __name__ == "__main__":
    asyncio.run(main())
