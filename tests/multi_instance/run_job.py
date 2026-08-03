"""다중 인스턴스 실증용 자식 프로세스 — 앱 서버 없이 잡/알림 경로만 실행한다.

두 모드:
  job      — `run_locked_job` 을 실행. advisory lock 을 **다른 프로세스**가 쥔 상태에서
             경합하는지 본다 (기존 B6 는 한 프로세스 안 세션 2개였다).
  cooldown — `alert._should_send` 를 같은 key 로 2회 호출. 쿨다운 상태가 프로세스
             로컬인지(= 다중 인스턴스면 인스턴스별로 따로 셈)를 실측한다.

프로세스 간 출발 동기화는 파일 신호로 한다. 파이프 readline 은 부모가 블로킹될 수
있고, "둘 다 import 를 끝낸 뒤 동시에 락을 시도"해야 경합이 성립하기 때문:
  1. import 완료 → `ready-<label>` 파일 생성
  2. 부모가 두 ready 를 확인하면 `go` 파일 생성
  3. 자식은 `go` 를 10ms 간격으로 폴링하다 출발

사용:
  python -u -m tests.multi_instance.run_job job <workdir> <label> <job_key> <hold_sec>
  python -u -m tests.multi_instance.run_job cooldown <workdir> <label> <alert_key>
"""
import asyncio
import os
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_DB_URL = os.environ.get("DATABASE_URL", "")
if "test_household" not in _DB_URL:
    raise SystemExit(f"테스트 DB 가 아니다 — 중단: {_DB_URL!r}")

from app.core.alert import _should_send  # noqa: E402
from app.core.scheduler import run_locked_job  # noqa: E402
from tests.fixtures.factory import user_factory  # noqa: E402

_POLL_INTERVAL = 0.01
_GO_TIMEOUT = 30.0


def _signal_ready_and_wait(workdir: Path, label: str) -> None:
    (workdir / f"ready-{label}").write_text("1", encoding="utf-8")
    go = workdir / "go"
    deadline = time.monotonic() + _GO_TIMEOUT
    while not go.exists():
        if time.monotonic() > deadline:
            raise SystemExit("go 신호 대기 타임아웃")
        time.sleep(_POLL_INTERVAL)


async def _run_job(job_key: str, hold_seconds: float) -> None:
    """락을 쥔 채 hold_seconds 만큼 머문다 — 경쟁 프로세스가 반드시 그 창에서 시도한다."""
    executed = False

    async def fn(session) -> None:
        nonlocal executed
        executed = True
        await user_factory(session)
        await asyncio.sleep(hold_seconds)

    await run_locked_job(job_key, fn)
    print("RAN" if executed else "SKIPPED")


def _run_cooldown(alert_key: str) -> None:
    """같은 key 2회 판정.

    `send_alert` 가 아니라 `_should_send` 를 직접 부르는 이유: DISCORD_WEBHOOK_URL 이
    빈 값이면 send_alert 가 쿨다운 판정 전에 return 해(short-circuit) 검증이 성립하지
    않는다. 실발송 없이 "상태가 어디 있는가"만 확인한다.
    """
    first = _should_send(alert_key)
    second = _should_send(alert_key)
    print(f"first={first} second={second}")


def main() -> None:
    mode, workdir_arg, label = sys.argv[1], sys.argv[2], sys.argv[3]
    workdir = Path(workdir_arg)

    if mode == "job":
        job_key, hold_seconds = sys.argv[4], float(sys.argv[5])
        _signal_ready_and_wait(workdir, label)
        asyncio.run(_run_job(job_key, hold_seconds))
    elif mode == "cooldown":
        _run_cooldown(sys.argv[4])
    else:
        raise SystemExit(f"알 수 없는 모드: {mode}")


if __name__ == "__main__":
    main()
