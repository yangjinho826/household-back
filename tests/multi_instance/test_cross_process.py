"""E. 다중 인스턴스 시나리오 — tests/SCENARIOS.md E 표 대조.

기존 A11(멱등성 동시 N발)·B6(잡 동시 진입)은 `ASGITransport` / 한 프로세스 안 세션
2개라, **한 프로세스·한 이벤트 루프** 안의 경합이었다. 코드가 주장하는 "다중 인스턴스"
(`scheduler.py` docstring)와 "인스턴스별로 따로 센다"(`alert.py` docstring)는 미검증
서술이었다. 이 모듈은 앱을 별도 OS 프로세스 2개로 띄워 그 경계를 실측한다.

검증하려는 가설: **상태를 DB 에 둔 것만 인스턴스 안전하다.**
  - 멱등성(ON CONFLICT 상태머신) / advisory lock → DB → 안전해야 한다 (E1·E2·E3)
  - 알림 쿨다운(프로세스 메모리 dict) → 안 되어야 한다 (E4)

**라우팅 증거**: 앞단에 LB 를 두지 않는다. 라운드로빈은 두 요청이 같은 인스턴스로 갈 수
있어 "서로 다른 프로세스가 경합했다"를 보장하지 못한다. 클라이언트가 포트를 직접 지정하고,
각 포트는 서로 다른 PID 가 바인딩하므로 **포트 지정이 곧 프로세스 지정**이다 (E0).
"""
import asyncio
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest_asyncio
from sqlalchemy import func, select

from app.core.database import async_session
from app.core.idempotency.model import IdempotencyRecord
from app.domain.transaction.model import Transaction
from app.domain.user.model import User
from tests.fixtures.factory import seed_transaction_context

_ROOT = Path(__file__).resolve().parents[2]
_LOG_DIR = _ROOT / "logs" / "multi-instance"  # logs/ 는 gitignore — 실증 캡처 보관용
_PORTS = (8101, 8102)
_BOOT_TIMEOUT_SECONDS = 60.0
_READY_TIMEOUT_SECONDS = 60.0
_JOB_HOLD_SECONDS = 2.0  # 락을 쥐고 머무는 시간 — 경쟁 프로세스가 이 창에서 시도한다


# ── 공용 헬퍼 ──

async def _count(model) -> int:
    """독립 세션으로 행 수를 센다 (다른 프로세스가 커밋한 결과를 봐야 한다)."""
    async with async_session() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _settled_count(model, expected: int, *, settle: float = 0.3, timeout: float = 5.0) -> int:
    """기대값 도달까지 폴링한 뒤, 도달 후에도 settle 만큼 더 지켜보고 최종값을 돌려준다.

    순간값을 단언하면 안 되는 이유(compose 실증에서 실측): **HTTP 200 수신이 DB 커밋
    가시성을 보장하지 않는다.** 보호를 끈 동일 하니스에서 응답 2건을 모두 받은 직후
    집계가 0/1/2 로 흔들렸다. 검증 대상은 순간 상태가 아니라 최종 상태다.

    도달 후 settle 재확인은 반대 방향 오판(늦게 한 건 더 들어오는데 먼저 통과)을 막는다.
    끝내 도달 못 하면 마지막 관측값을 그대로 돌려줘 호출부 단언이 실제 숫자로 실패한다.
    """
    deadline = time.monotonic() + timeout
    while True:
        count = await _count(model)
        if count == expected:
            await asyncio.sleep(settle)
            return await _count(model)
        if time.monotonic() >= deadline:
            return count
        await asyncio.sleep(0.05)


async def _post_create(base_url: str, ctx, *, key: str | None):
    """실 HTTP 로 POST /transaction/create. key=None 이면 멱등 보호를 끈 상태."""
    headers = dict(ctx.auth_headers)
    if key is not None:
        headers["Idempotency-Key"] = key
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        return await client.post("/transaction/create", json=ctx.create_body(), headers=headers)


def _child_env() -> dict[str, str]:
    """conftest 가 .env.test 로 덮어쓴 os.environ 을 그대로 물려준다.

    자식은 conftest 를 타지 않으므로 이 상속이 유일한 설정 경로다. 자식 엔트리에도
    DATABASE_URL 가드가 있어 운영 DB 접속은 이중으로 막힌다.
    """
    return os.environ.copy()


# ── 인스턴스 fixture ──

@dataclass
class Instances:
    procs: list[subprocess.Popen]
    base_urls: list[str]
    log_paths: list[Path]


def _spawn_instance(port: int) -> tuple[subprocess.Popen, Path, object]:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOG_DIR / f"instance-{port}.log"
    handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "tests.multi_instance.run_instance", str(port)],
        cwd=str(_ROOT),
        env=_child_env(),
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    return proc, log_path, handle


async def _wait_ready(base_url: str, proc: subprocess.Popen, log_path: Path) -> None:
    deadline = time.monotonic() + _BOOT_TIMEOUT_SECONDS
    async with httpx.AsyncClient(base_url=base_url, timeout=2.0) as client:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"인스턴스가 조기 종료됐다 (exit={proc.returncode})\n"
                    f"--- {log_path.name} ---\n{log_path.read_text(encoding='utf-8', errors='replace')}",
                )
            try:
                if (await client.get("/health")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.2)
    raise RuntimeError(f"인스턴스 기동 타임아웃: {base_url}")


@pytest_asyncio.fixture(scope="module")
async def instances():
    """uvicorn 인스턴스 2개를 띄우고 모듈 전체에서 재사용한다."""
    spawned = [_spawn_instance(port) for port in _PORTS]
    base_urls = [f"http://127.0.0.1:{port}" for port in _PORTS]
    try:
        for base_url, (proc, log_path, _) in zip(base_urls, spawned, strict=True):
            await _wait_ready(base_url, proc, log_path)
        yield Instances(
            procs=[proc for proc, _, _ in spawned],
            base_urls=base_urls,
            log_paths=[log_path for _, log_path, _ in spawned],
        )
    finally:
        for proc, _, handle in spawned:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
            handle.close()


# ── E0: 전제 — 정말 서로 다른 프로세스인가 ──

async def test_E0_두_인스턴스는_서로_다른_프로세스다(instances):
    """이 단언이 깨지면 이하 모든 시나리오의 '다중 인스턴스'가 성립하지 않는다."""
    assert len({proc.pid for proc in instances.procs}) == 2

    for base_url in instances.base_urls:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            assert (await client.get("/health")).status_code == 200


# ── E1: 멱등성 크로스 인스턴스 ──

async def test_E1_동일키를_두_인스턴스에_동시_투입해도_거래_1건(db, instances):
    ctx = await seed_transaction_context(db)
    key = f"e1-{uuid.uuid4().hex[:8]}"

    results = await asyncio.gather(
        *[_post_create(url, ctx, key=key) for url in instances.base_urls],
        return_exceptions=True,
    )

    assert await _settled_count(Transaction, 1) == 1
    assert await _settled_count(IdempotencyRecord, 1) == 1

    codes = [r.status_code for r in results if hasattr(r, "status_code")]
    assert len(codes) == 2, f"두 요청 모두 응답해야 함 (results={results})"
    assert 200 in codes, f"성공 응답 하나는 있어야 함 (codes={codes})"
    # 나머지는 캐시 재생(200) 또는 PENDING 중 재진입(409/ID003) — 계약상 이 둘뿐이다.
    assert set(codes) <= {200, 409}, f"예상 밖 응답 (codes={codes})"

    # 라우팅 증거: 두 인스턴스가 각각 이 요청을 자기 프로세스에서 처리했다.
    # 증거 문자열이 경로별로 다른 이유(실증 중 발견) — `main.py` 의 add_middleware 순서상
    # IdempotencyMiddleware 가 AccessLogMiddleware 보다 **바깥**이라, 캐시 히트로 반환되는
    # 재시도 요청은 access log 를 타지 않고 서비스 로그(`idempotency cache hit: key=...`)에만
    # 남는다. 즉 멱등 재시도는 access log 에 안 보인다.
    for log_path in instances.log_paths:
        log = log_path.read_text(encoding="utf-8", errors="replace")
        handled = "POST /transaction/create" in log or f"key={key}" in log
        assert handled, f"{log_path.name} 에 이 요청의 처리 기록 없음"


async def test_E1nc_보호_끄면_두_인스턴스가_2건을_만든다(db, instances):
    """negative control — E1 의 1건이 '요청이 순차로 처리돼서'가 아님을 역증명한다.

    같은 하니스(두 인스턴스 동시 투입)에서 Idempotency-Key 만 빼면 2건이 생긴다.
    """
    ctx = await seed_transaction_context(db)

    await asyncio.gather(
        *[_post_create(url, ctx, key=None) for url in instances.base_urls],
        return_exceptions=True,
    )

    assert await _settled_count(Transaction, 2) == 2
    assert await _settled_count(IdempotencyRecord, 0) == 0


async def test_E2_10발을_두_인스턴스에_분배해도_거래_1건(db, instances):
    """A11 의 N=10 을 프로세스 경계 너머로 확장 — 5:5 로 나눠 동시 투입."""
    ctx = await seed_transaction_context(db)
    key = f"e2-{uuid.uuid4().hex[:8]}"
    urls = [instances.base_urls[i % 2] for i in range(10)]

    results = await asyncio.gather(
        *[_post_create(url, ctx, key=key) for url in urls],
        return_exceptions=True,
    )

    assert await _settled_count(Transaction, 1) == 1
    assert await _settled_count(IdempotencyRecord, 1) == 1
    codes = [r.status_code for r in results if hasattr(r, "status_code")]
    assert set(codes) <= {200, 409}, f"예상 밖 응답 (codes={codes})"


# ── E3: advisory lock 크로스 프로세스 ──

def _wait_ready_files(workdir: Path, labels: tuple[str, ...]) -> None:
    """두 자식이 import 를 끝낼 때까지 대기 — 그래야 '동시 출발'이 성립한다."""
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if all((workdir / f"ready-{label}").exists() for label in labels):
            return
        time.sleep(0.02)
    raise RuntimeError("자식 프로세스 ready 신호 타임아웃")


def _run_children(mode: str, workdir: Path, labels: tuple[str, ...], extra: list[str]) -> list[str]:
    """자식 2개를 띄우고 ready 를 기다렸다가 동시에 출발시킨 뒤 출력을 모은다."""
    procs = []
    for label in labels:
        out_path = workdir / f"out-{label}.log"
        handle = out_path.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "tests.multi_instance.run_job", mode,
             str(workdir), label, *extra],
            cwd=str(_ROOT),
            env=_child_env(),
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        procs.append((proc, handle, out_path))

    _wait_ready_files(workdir, labels)
    (workdir / "go").write_text("1", encoding="utf-8")

    outputs = []
    for proc, handle, out_path in procs:
        proc.wait(timeout=120)
        handle.close()
        outputs.append(out_path.read_text(encoding="utf-8", errors="replace").strip())
    return outputs


async def test_E3_다른_프로세스의_같은_잡은_하나만_실행된다(instances):
    """B6(한 프로세스 안 세션 2개)을 프로세스 경계 너머로 확장.

    `scheduler.py` 가 주장하는 "같은 잡이 다중 인스턴스/워커에서 동시 진입해도 1개만
    통과"의 직접 증거. 두 인스턴스가 각자 APScheduler 를 띄우는 현재 구조에서 같은
    cron 이 양쪽에 발사되는 상황과 같다.
    """
    job_key = f"proof-{uuid.uuid4().hex[:12]}"  # advisory lock 은 DB 전역 네임스페이스
    workdir = _LOG_DIR / f"job-{uuid.uuid4().hex[:8]}"
    workdir.mkdir(parents=True, exist_ok=True)

    outputs = _run_children("job", workdir, ("a", "b"), [job_key, str(_JOB_HOLD_SECONDS)])
    verdicts = [out.splitlines()[-1].strip() if out else "<빈 출력>" for out in outputs]

    assert sorted(verdicts) == ["RAN", "SKIPPED"], f"정확히 하나만 실행돼야 함 (outputs={outputs})"
    assert await _settled_count(User, 1) == 1  # 실행된 쪽이 쓴 행만 남는다


# ── E4: 인스턴스 안전하지 "않은" 것 — 알림 쿨다운 ──

async def test_E4_알림_쿨다운은_프로세스별로_따로_센다(tmp_path):
    """`alert.py` 가 주석으로만 서술하던 한계를 실측한다.

    쿨다운 상태가 공유(DB/Redis)라면 두 번째 프로세스의 첫 호출은 False 여야 한다.
    실제로는 두 프로세스 모두 first=True — **상태가 프로세스 메모리에 있기 때문**이다.
    같은 장애가 인스턴스 수만큼 알림을 만든다는 뜻이고, 이것이 E1~E3(상태가 DB)와
    갈리는 경계다.
    """
    alert_key = f"proof-{uuid.uuid4().hex[:8]}"
    outputs = []
    for label in ("a", "b"):
        out_path = tmp_path / f"cooldown-{label}.log"
        with out_path.open("w", encoding="utf-8") as handle:
            subprocess.run(
                [sys.executable, "-u", "-m", "tests.multi_instance.run_job", "cooldown",
                 str(tmp_path), label, alert_key],
                cwd=str(_ROOT),
                env=_child_env(),
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=True,
            )
        outputs.append(out_path.read_text(encoding="utf-8", errors="replace").strip())

    for label, out in zip(("a", "b"), outputs, strict=True):
        assert "first=True second=False" in out, f"프로세스 {label} 출력: {out!r}"
