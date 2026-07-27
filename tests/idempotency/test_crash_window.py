"""C. fault-injection — crash window 자백 테스트 (tests/SCENARIOS.md C 표).

**이 파일의 RED 는 수정 대상이 아니라 자백 대상이다.** A·B 가 "계약이 지켜짐"을
증명했다면, C 는 계약이 안 지켜지는 구간을 통과하는 테스트로 박제한다.

박제 대상 — `app/core/idempotency/middleware.py:92-109`:
    response = await call_next(request)          # 라우터 실행 → 비즈 tx COMMIT
    captured_body = await capture_response_body(response)
                                                 # ←── crash window
    await idempotency_service.mark_completed(..)  # 멱등 레코드는 아직 PENDING
    await session.commit()

비즈 데이터는 커밋됐는데 멱등 레코드가 COMPLETED 가 아닌 구간. 여기서 프로세스가
죽으면 except 블록의 release 조차 못 돌아 PENDING 이 잔류하고, TTL(60초) 후
cleanup 이 지우면 같은 키 재시도가 라우터를 다시 태운다 → 중복 생성.

**용어 정직성(codex 지적 채택)**: 진짜 fault injection 은 C1 뿐이다. C2·C3 는 DB 를
crash 직후 상태로 직접 만드는 **state-based simulation** — 실제 SIGKILL 은 release 조차
못 도는데 예외 주입은 release 를 타므로, 그 상태는 주입으로 재현되지 않기 때문이다.
상태를 직접 심는 방식은 A8 과 동일하고 순서 의존이 없어 결정적이다.

**왜 3개로 충분한가**: 미들웨어의 다른 crash 지점(capture_response_body 중 / mark_completed
후 commit 전 / release 전후 / acquire 직후)은 모두 최종 DB 상태가 C1(레코드 0건 + 거래 잔류)
아니면 C2(PENDING 잔류) 로 수렴한다. 재시도 결과를 가르는 건 crash 시각이 아니라 **남은
레코드 상태**뿐이므로, 그 두 상태를 덮으면 경우의 수가 닫힌다.
"""
import uuid
from datetime import datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.core.database import async_session
from app.core.idempotency import service as idempotency_service
from app.core.idempotency.constants import PENDING_TTL_SECONDS
from app.core.idempotency.model import IdempotencyRecord
from app.domain.transaction.model import Transaction
from app.main import app
from tests.fixtures.factory import seed_transaction_context


async def _count(model) -> int:
    """독립 세션으로 행 수를 센다 (read committed → 다른 세션의 커밋 반영)."""
    async with async_session() as session:
        result = await session.execute(select(func.count()).select_from(model))
        return result.scalar_one()


async def _post(ctx, key: str, *, raise_app_exceptions: bool = True):
    headers = {**ctx.auth_headers, "Idempotency-Key": key}
    transport = ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post("/transaction/create", json=ctx.create_body(), headers=headers)


async def _simulate_crash_before_completed() -> None:
    """COMPLETED 직전에 죽은 상태를 재현 — 레코드를 PENDING 으로 되돌린다.

    실제 crash 는 mark_completed 가 아예 안 돈 상태이므로, 응답 캐시 컬럼도 전부 비운다.
    """
    async with async_session() as session:
        await session.execute(
            update(IdempotencyRecord).values(
                status="PENDING",
                status_code=None,
                response_headers=None,
                response_body=None,
                completed_at=None,
            ),
        )
        await session.commit()


async def _expire_pending_and_cleanup() -> None:
    """PENDING TTL 을 넘긴 것처럼 created_at 을 밀고 cleanup 잡 로직을 직접 호출한다."""
    async with async_session() as session:
        await session.execute(
            update(IdempotencyRecord).values(
                created_at=datetime.now() - timedelta(seconds=PENDING_TTL_SECONDS + 60),
            ),
        )
        await session.commit()

    async with async_session() as session:
        await idempotency_service.cleanup_expired(session)
        await session.commit()


# ── C1: mark_completed 예외 주입 (라우터는 정상 완료) ──

async def test_C1_완료표시_직전_예외는_해제되고_재시도가_라우터를_다시_태운다(db, mocker):
    ctx = await seed_transaction_context(db)
    key = f"key-c1-{uuid.uuid4().hex[:8]}"

    mocker.patch(
        "app.core.idempotency.service.mark_completed",
        side_effect=RuntimeError("crash before COMPLETED"),
    )
    failed = await _post(ctx, key, raise_app_exceptions=False)

    assert failed.status_code == 500
    assert await _count(IdempotencyRecord) == 0  # except 블록의 release 가 돌았다

    # **실측**: 500 을 받았는데도 거래는 남아 있다. call_next 가 돌아온 시점엔 라우터의
    # 비즈 트랜잭션이 이미 커밋된 뒤라, 미들웨어에서 터진 예외는 그걸 되돌리지 못한다.
    # A9(라우터 자체가 실패)는 0건이었던 것과 갈리는 지점 = crash window 가 실재한다는 증거.
    assert await _count(Transaction) == 1

    # 같은 키 재시도 → 락이 풀려 있어 라우터가 다시 실행된다
    mocker.stopall()
    retried = await _post(ctx, key)

    assert retried.status_code == 200
    assert await _count(Transaction) == 2  # ← 자백: 같은 키인데 거래가 2건


# ── C2: crash 잔류 PENDING 은 재시도를 막는다 ──

async def test_C2_크래시로_남은_PENDING은_재시도를_차단한다(db):
    ctx = await seed_transaction_context(db)
    key = f"key-c2-{uuid.uuid4().hex[:8]}"

    first = await _post(ctx, key)
    assert first.status_code == 200
    assert await _count(Transaction) == 1

    await _simulate_crash_before_completed()

    # 정당한 재시도인데도 처리 중으로 보여 막힌다 — TTL(60초) 동안
    blocked = await _post(ctx, key)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "ID003"
    assert await _count(Transaction) == 1


# ── C3: TTL 만료 후 재시도는 중복을 만든다 (exactly-once 아님) ──

async def test_C3_TTL_만료_후_재시도는_거래를_중복_생성한다(db):
    ctx = await seed_transaction_context(db)
    key = f"key-c3-{uuid.uuid4().hex[:8]}"

    first = await _post(ctx, key)
    assert first.status_code == 200
    assert await _count(Transaction) == 1

    await _simulate_crash_before_completed()
    await _expire_pending_and_cleanup()
    assert await _count(IdempotencyRecord) == 0  # cleanup 이 잔류 PENDING 을 지웠다

    # 멱등 흔적이 사라졌으니 같은 키·같은 body 여도 라우터가 다시 돈다
    retried = await _post(ctx, key)

    assert retried.status_code == 200
    assert await _count(Transaction) == 2  # ← 자백: exactly-once 가 아니다
