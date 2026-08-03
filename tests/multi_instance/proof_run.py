"""compose 다중 인스턴스 실증 러너 — 운영 이미지·entrypoint 로 뜬 인스턴스 2개에 투입한다.

pytest(`test_cross_process.py`)는 회귀 게이트고, 이 스크립트는 **운영 구성 재현** 이다.
같은 명제를 다른 층위에서 확인한다:
  pytest  — uvicorn 프로세스 2개 (호스트, 개발 의존성 포함)
  이 스크립트 — Docker 이미지 2개 (entrypoint.sh → alembic → uvicorn, 컨테이너 경계)

앱 이미지 안에서 실행한다 (compose 네트워크의 서비스명으로 접근):
  docker compose -f docker-compose.multi.yml run --rm --entrypoint "" app1 \
      /app/.venv/bin/python -m tests.multi_instance.proof_run
"""
import asyncio
import time
import uuid

import httpx
from sqlalchemy import func, select, text

from app.core.database import async_session, engine
from app.core.idempotency.model import IdempotencyRecord
from app.core.model import Base
from app.domain.transaction.model import Transaction
from app.main import app  # noqa: F401  — 전 도메인 모델을 Base.metadata 에 등록
from tests.fixtures.factory import seed_transaction_context

# LB 를 두지 않는다 — 라운드로빈은 두 요청이 같은 인스턴스로 갈 수 있어 경합을 보장 못 한다.
# 서비스명이 각 컨테이너를 직접 가리키므로 "주소 지정 = 인스턴스 지정".
INSTANCES = ("http://app1:8000", "http://app2:8000")


async def _count(model) -> int:
    async with async_session() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _settled_count(model, expected: int, *, settle: float = 0.3, timeout: float = 5.0) -> int:
    """기대값 도달까지 폴링 후 settle 만큼 더 지켜보고 최종값을 반환.

    HTTP 200 수신이 DB 커밋 가시성을 보장하지 않는다 — 아래 '거래 행(즉시)' 가 그 증거다.
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


async def _reset() -> None:
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


async def _seed():
    async with async_session() as session:
        return await seed_transaction_context(session)


async def _post(base_url: str, ctx, *, key: str | None):
    headers = dict(ctx.auth_headers)
    if key is not None:
        headers["Idempotency-Key"] = key
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        return await client.post("/transaction/create", json=ctx.create_body(), headers=headers)


async def _client_addrs() -> list[str]:
    """이 DB 에 붙어 있는 커넥션의 출처 — 인스턴스 2개가 각자 붙었음을 보여준다."""
    async with async_session() as session:
        rows = await session.execute(
            text(
                "SELECT DISTINCT client_addr::text FROM pg_stat_activity "
                "WHERE datname = current_database() AND client_addr IS NOT NULL "
                "ORDER BY 1",
            ),
        )
        return [row[0] for row in rows]


async def _scenario(title: str, *, key: str | None, expected_transactions: int) -> bool:
    await _reset()
    ctx = await _seed()

    results = await asyncio.gather(
        *[_post(url, ctx, key=key) for url in INSTANCES], return_exceptions=True,
    )
    codes = [r.status_code if hasattr(r, "status_code") else repr(r) for r in results]
    returned_ids = [
        (r.json().get("data") or {}).get("id") for r in results if hasattr(r, "json")
    ]

    immediate = await _count(Transaction)  # 응답 직후 순간값 — 커밋 가시성 창의 증거
    transactions = await _settled_count(Transaction, expected_transactions)
    records = await _count(IdempotencyRecord)
    ok = transactions == expected_transactions

    print(f"\n[{title}]")
    print(f"  투입           : {len(INSTANCES)}건 동시 (인스턴스별 1건)")
    print(f"  Idempotency-Key: {key or '(없음 — 보호 끔)'}")
    print(f"  응답 코드      : {codes}")
    print(f"  응답 거래 ID   : {returned_ids}")
    print(f"  거래 행(즉시)  : {immediate}")
    print(f"  거래 행(최종)  : {transactions} (기대 {expected_transactions})")
    print(f"  멱등 레코드    : {records}")
    print(f"  판정           : {'PASS' if ok else 'FAIL'}")
    return ok


async def main() -> None:
    print("=" * 68)
    print("다중 인스턴스 멱등성 실증 (compose — 운영 이미지)")
    print("=" * 68)
    print(f"인스턴스: {', '.join(INSTANCES)}")
    print(f"DB 커넥션 출처: {await _client_addrs()}")

    passed = await _scenario("M1 · 동일 키를 두 인스턴스에 동시 투입", key=f"proof-{uuid.uuid4().hex[:8]}", expected_transactions=1)
    passed &= await _scenario("M1-nc · 보호를 끄고 동일 하니스", key=None, expected_transactions=2)

    await _reset()
    await engine.dispose()
    print("\n" + "=" * 68)
    print("종합: " + ("전부 PASS" if passed else "실패 있음"))
    print("=" * 68)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
