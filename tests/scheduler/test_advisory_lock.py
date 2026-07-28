"""B. advisory lock 시나리오 — tests/SCENARIOS.md B 표 대조.

`app/core/scheduler.py` 의 try_advisory_lock / run_locked_job 공개계약을 검증한다.
락이 트랜잭션 스코프라 경합을 만들려면 **세션1 이 tx 를 연 상태 그대로** 세션2 가
시도해야 한다 — 중첩 `async with` 로 그 상태를 유지한다.

행 수 집계는 독립 세션(`_count_users`)으로 돈다. run_locked_job 이 자체 세션에서
commit/rollback 하므로, 커밋 반영 여부는 다른 커넥션에서 봐야 의미가 있다.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text

from app.core.database import async_session
from app.core.scheduler import run_locked_job, try_advisory_lock
from app.domain.user.model import User
from tests.fixtures.factory import user_factory


def _job_key() -> str:
    """테스트마다 유니크한 잡 이름 — advisory lock 은 DB 전역이라 고정 키면 서로 간섭한다."""
    return f"job-{uuid.uuid4().hex[:12]}"


async def _count_users() -> int:
    async with async_session() as session:
        return (await session.execute(select(func.count()).select_from(User))).scalar_one()


async def _backend_pid(session) -> int:
    """이 세션이 붙은 PG 백엔드 프로세스 id — 두 세션이 진짜 다른 커넥션인지 확인용."""
    return (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()


# ── try_advisory_lock (B1~B3): 락 판정 자체 ──

async def test_B1_다른_세션_같은_키는_하나만_획득한다():
    key = _job_key()
    async with async_session() as first, async_session() as second:
        async with first.begin():
            assert await try_advisory_lock(first, key) is True
            async with second.begin():
                # 커넥션이 같으면 advisory lock 은 재진입 허용(B1-nc) → 경합 자체가 성립 안 한다.
                assert await _backend_pid(first) != await _backend_pid(second)
                assert await try_advisory_lock(second, key) is False  # 대기 없이 즉시 False


async def test_B1nc_같은_세션은_같은_키를_다시_획득한다():
    """negative control — 판정 단위가 커넥션임을 보여 B1 의 False 가 상수값이 아님을 역증명."""
    key = _job_key()
    async with async_session() as session:
        async with session.begin():
            assert await try_advisory_lock(session, key) is True
            assert await try_advisory_lock(session, key) is True


async def test_B2_다른_키는_두_세션_모두_획득한다():
    async with async_session() as first, async_session() as second:
        async with first.begin():
            assert await try_advisory_lock(first, _job_key()) is True
            async with second.begin():
                assert await try_advisory_lock(second, _job_key()) is True


async def test_B3_트랜잭션_종료_후_같은_키를_재획득한다():
    key = _job_key()
    async with async_session() as first:
        async with first.begin():
            assert await try_advisory_lock(first, key) is True
        # begin 블록 이탈 = commit → xact 스코프 락이 명시 unlock 없이 풀린다

    async with async_session() as second:
        async with second.begin():
            assert await try_advisory_lock(second, key) is True


# ── run_locked_job (B4~B5): skip / 예외 계약 ──

async def test_B4_락이_선점되면_잡을_건너뛴다():
    key = _job_key()
    calls: list[int] = []

    async def job(session):
        calls.append(1)
        await user_factory(session)

    async with async_session() as holder:
        async with holder.begin():
            assert await try_advisory_lock(holder, key) is True
            await run_locked_job(key, job)  # 예외 없이 조용히 skip

    assert calls == []
    assert await _count_users() == 0


async def test_B4nc_선점이_없으면_잡이_실행되고_커밋된다():
    """negative control — B4 의 '미호출'이 락 때문임을 역증명."""
    key = _job_key()
    calls: list[int] = []

    async def job(session):
        calls.append(1)
        await user_factory(session)

    await run_locked_job(key, job)

    assert calls == [1]
    assert await _count_users() == 1


async def test_B6_동시_실행되는_같은_잡은_하나만_통과한다():
    """계약의 '다중 인스턴스·워커 동시 진입 시 1개만 통과'를 run_locked_job 레벨에서 검증.

    Event 로 순서를 고정해 flaky 를 없앤다 — 두 번째 시도는 첫 잡이 락을 **쥐고 있는 동안**
    일어나고, 첫 잡은 두 번째가 판정을 끝낸 뒤에야 진행한다.
    """
    key = _job_key()
    calls: list[str] = []
    lock_held = asyncio.Event()
    rival_done = asyncio.Event()

    async def holder_job(session):
        calls.append("holder")
        lock_held.set()
        await rival_done.wait()
        await user_factory(session)

    async def rival_job(session):
        calls.append("rival")

    async def run_rival():
        await lock_held.wait()
        await run_locked_job(key, rival_job)
        rival_done.set()

    await asyncio.gather(run_locked_job(key, holder_job), run_rival())

    assert calls == ["holder"]        # 경쟁자는 fn 진입조차 못 함
    assert await _count_users() == 1  # 통과한 1개의 작업만 커밋


async def test_B5_잡_예외는_재발생하고_변경은_롤백된다():
    key = _job_key()

    async def job(session):
        await user_factory(session)
        raise RuntimeError("잡 내부 실패")

    with pytest.raises(RuntimeError, match="잡 내부 실패"):
        await run_locked_job(key, job)

    assert await _count_users() == 0
