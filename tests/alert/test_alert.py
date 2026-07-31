"""장애 알림(app/core/alert.py) 시나리오 — 요구사항에서 도출.

계약:
- 미설정(빈 URL)이면 발송 자체가 없다 — 알림 없이도 앱은 완전하게 돈다.
- 같은 key 는 쿨다운 내 1회만, 다른 key 는 독립.
- 발송 실패는 절대 호출자로 전파되지 않는다 (본 흐름 격리).
- run_locked_job 실패는 알림을 쏘고 예외를 그대로 재발생한다 (스케줄러 계약 유지).
"""
import asyncio
import uuid

import pytest

from app.core import alert
from app.core.config import settings
from app.core.scheduler import run_locked_job


@pytest.fixture(autouse=True)
def _reset_cooldown():
    """쿨다운은 모듈 전역 상태 — 테스트 간 간섭 차단."""
    alert._last_sent_at.clear()
    yield
    alert._last_sent_at.clear()


@pytest.fixture
def sent(monkeypatch):
    """실 발송(_deliver)을 기록기로 교체 + webhook 설정 상태로 만든다."""
    calls: list[tuple[str, str]] = []

    async def _record(key: str, message: str) -> None:
        calls.append((key, message))

    monkeypatch.setattr(alert, "_deliver", _record)
    monkeypatch.setattr(settings, "DISCORD_WEBHOOK_URL", "https://discord.invalid/hook")
    return calls


async def test_웹훅_미설정이면_발송하지_않는다(monkeypatch):
    calls = []

    async def _record(key, message):
        calls.append(key)

    monkeypatch.setattr(alert, "_deliver", _record)
    monkeypatch.setattr(settings, "DISCORD_WEBHOOK_URL", "")

    await alert.send_alert("k", "m")
    alert.send_alert_background("k", "m")
    await asyncio.sleep(0)

    assert calls == []
    assert alert._last_sent_at == {}  # 쿨다운 기록조차 안 남긴다


async def test_같은_키는_쿨다운_내_1회만_발송한다(sent):
    await alert.send_alert("dup", "첫 번째")
    await alert.send_alert("dup", "두 번째")

    assert len(sent) == 1
    assert sent[0][1] == "첫 번째"


async def test_다른_키는_각각_발송한다(sent):
    await alert.send_alert("a", "m1")
    await alert.send_alert("b", "m2")

    assert [c[0] for c in sent] == ["a", "b"]


async def test_쿨다운이_지나면_같은_키도_재발송한다(sent, monkeypatch):
    await alert.send_alert("k", "first")
    # 시간을 돌리는 대신 기록된 타임스탬프를 쿨다운 이전으로 밀어낸다
    alert._last_sent_at["k"] -= alert._COOLDOWN_SECONDS + 1

    await alert.send_alert("k", "second")

    assert len(sent) == 2


async def test_발송_실패는_호출자로_전파되지_않는다(monkeypatch, caplog):
    """_deliver 를 진짜로 태우고 HTTP 레이어만 죽인다 — try/except 격리 자체를 검증."""

    class _BrokenClient:
        def __init__(self, *args, **kwargs):
            raise ConnectionError("network down")

    monkeypatch.setattr(settings, "DISCORD_WEBHOOK_URL", "https://discord.invalid/hook")
    monkeypatch.setattr(alert.httpx, "AsyncClient", _BrokenClient)

    await alert.send_alert("k", "m")  # 예외가 새면 여기서 테스트가 터진다

    assert "Discord 알림 발송 실패" in caplog.text


async def test_background_는_task_로_발송된다(sent):
    alert.send_alert_background("bg", "m")
    await asyncio.sleep(0)  # fire-and-forget task 에 실행 기회

    assert sent == [("bg", "m")]


async def test_background_쿨다운_차단은_task_를_만들지_않는다(sent):
    """5xx 폭주 방어 — 판정이 create_task 앞이라 task 자체가 안 생긴다."""
    alert.send_alert_background("burst", "m1")
    before = len(alert._background_tasks)
    alert.send_alert_background("burst", "m2")

    assert len(alert._background_tasks) == before  # 두 번째는 task 미생성
    await asyncio.sleep(0)
    assert len(sent) == 1


# ── run_locked_job wiring (실 PG 하니스 — scheduler 테스트와 동일 계약 위) ──

async def test_잡_실패는_알림을_쏘고_예외를_재발생한다(sent):
    job_name = f"job-{uuid.uuid4().hex[:12]}"

    async def broken_job(session):
        raise RuntimeError("잡 내부 실패")

    with pytest.raises(RuntimeError, match="잡 내부 실패"):
        await run_locked_job(job_name, broken_job)

    assert len(sent) == 1
    key, message = sent[0]
    assert key == f"job:{job_name}"
    assert job_name in message


async def test_락_선점_skip_은_알림을_쏘지_않는다(sent):
    """skip 은 정상 동작(다른 워커가 이미 실행 중) — 알림 대상이 아니다."""
    from app.core.database import async_session
    from app.core.scheduler import try_advisory_lock

    job_name = f"job-{uuid.uuid4().hex[:12]}"

    async def job(session):
        pass

    async with async_session() as holder:
        async with holder.begin():
            assert await try_advisory_lock(holder, job_name) is True
            await run_locked_job(job_name, job)

    assert sent == []
