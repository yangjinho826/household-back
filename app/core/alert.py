"""장애 알림 — Discord webhook 발송.

알림은 본 흐름의 보조 채널이다. 그래서 두 가지를 구조로 강제한다:
- DISCORD_WEBHOOK_URL 미설정이면 no-op — 알림 없이도 앱은 완전하게 돈다.
- 발송 실패는 로그만 남긴다 — 알림 경로의 장애가 잡/요청 처리를 절대 깨지 않는다.

같은 key 는 쿨다운으로 묶는다. 5xx 폭주 시 Discord rate limit(30/min)에 걸려
정작 중요한 알림이 막히는 것과 알림 피로를 동시에 방어한다. in-memory dict 라
다중 인스턴스면 인스턴스별로 따로 세지만, key 집합이 유한(unhandled/http5xx/job:*)
하고 단일 인스턴스 운영이라 감수한다.
"""
import asyncio
import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_COOLDOWN_SECONDS = 300
_TIMEOUT_SECONDS = 5
_MAX_MESSAGE_LENGTH = 500  # Discord 2000자 제한 + 예외 repr 에 섞이는 내부 정보 노출 최소화

_last_sent_at: dict[str, float] = {}
# fire-and-forget task 는 참조를 쥐고 있지 않으면 GC 대상이 돼 발송 전에 사라질 수 있다
_background_tasks: set[asyncio.Task] = set()


def _should_send(key: str) -> bool:
    """쿨다운 판정 + 통과 시 타임스탬프 갱신.

    동기 함수인 게 중요 — send_alert_background 가 task 생성 전에 판정해야
    5xx 폭주 시 요청마다 task 가 쌓이는 것 자체를 막는다.
    """
    now = time.monotonic()
    last = _last_sent_at.get(key)
    if last is not None and now - last < _COOLDOWN_SECONDS:
        return False
    _last_sent_at[key] = now
    return True


async def _deliver(key: str, message: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            await client.post(
                settings.DISCORD_WEBHOOK_URL,
                json={"content": f"🚨 household | {message}"[:_MAX_MESSAGE_LENGTH]},
            )
    except Exception:
        logger.warning("Discord 알림 발송 실패 (key=%s)", key, exc_info=True)


async def send_alert(key: str, message: str) -> None:
    """Discord 로 장애 알림. 미설정/쿨다운/발송 실패 모두 조용히 넘어간다."""
    if not settings.DISCORD_WEBHOOK_URL or not _should_send(key):
        return
    await _deliver(key, message)


def send_alert_background(key: str, message: str) -> None:
    """요청 경로용 fire-and-forget — 응답을 발송 타임아웃만큼 붙잡지 않는다.

    셧다운 시점에 미발송 task 는 유실될 수 있다. 서버 종료 순간의 알림까지
    보장하는 건 서버 발신 구조로는 불가능하고, 그 영역은 외부 감시
    (UptimeRobot /health 폴링)가 담당한다.
    """
    if not settings.DISCORD_WEBHOOK_URL or not _should_send(key):
        return
    task = asyncio.get_running_loop().create_task(_deliver(key, message))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
