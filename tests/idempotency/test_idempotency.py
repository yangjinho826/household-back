"""A. 멱등성 시나리오 — tests/SCENARIOS.md A 표 대조.

멱등성 미들웨어(app/core/idempotency)의 공개계약을 검증한다.
성공 응답은 HTTP 200(ApiResponse.ok) — 라우터에 status_code 지정이 없어 201 아님.

집계(_count)·레코드 조회(_fetch_record)는 **독립 세션**으로 돈다. db fixture 세션에서
rollback/조회를 하면 seed 로 만든 ctx.user 등이 expire 돼 이후 user.id 접근 시
MissingGreenlet(sync 컨텍스트 lazy load)이 터지기 때문.
"""
import asyncio
import hashlib
import json
import uuid
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, insert, select

from app.core.database import async_session
from app.core.idempotency.model import IdempotencyRecord
from app.domain.transaction.model import Transaction
from app.main import app
from tests.fixtures.factory import seed_transaction_context


async def _count(model) -> int:
    """독립 세션으로 행 수를 센다 (read committed → 다른 세션의 커밋 반영)."""
    async with async_session() as session:
        result = await session.execute(select(func.count()).select_from(model))
        return result.scalar_one()


async def _fetch_record(model):
    """독립 세션으로 단일 행을 로드 (expire_on_commit=False 라 close 후에도 값 유지)."""
    async with async_session() as session:
        return (await session.execute(select(model))).scalar_one()


async def _post_create(ctx, *, key: str | None = None, body: dict | None = None):
    """독립 client/transport 로 POST /transaction/create.

    동시성 테스트에서 각 요청이 진짜 독립 커넥션을 타도록 매 호출 새 client 를 연다.
    key=None 이면 Idempotency-Key 헤더를 안 붙인다(A11-nc: 보호 끈 상태).
    """
    headers = dict(ctx.auth_headers)
    if key is not None:
        headers["Idempotency-Key"] = key
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post(
            "/transaction/create", json=body or ctx.create_body(), headers=headers,
        )


# ── 게이트 (A1~A3): 3조건 미통과 시 멱등 레코드 안 생김 ──

async def test_A1_GET은_멱등성_미적용(client, db):
    await seed_transaction_context(db)
    resp = await client.get("/health", headers={"Idempotency-Key": "k-a1"})
    assert resp.status_code == 200
    assert await _count(IdempotencyRecord) == 0


async def test_A2_키_없으면_미적용(client, db):
    ctx = await seed_transaction_context(db)
    resp = await client.post(
        "/transaction/create", json=ctx.create_body(), headers=ctx.auth_headers,
    )
    assert resp.status_code == 200
    assert await _count(Transaction) == 1        # 거래는 정상 생성
    assert await _count(IdempotencyRecord) == 0  # 멱등 레코드는 없음


async def test_A3_JWT_없으면_미적용(db):
    ctx = await seed_transaction_context(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/transaction/create",
            json=ctx.create_body(),
            headers={"Idempotency-Key": "k-a3", "X-Household-Id": str(ctx.household.id)},
        )
    assert resp.status_code in (401, 403)             # 라우터 인증 단계서 거부
    assert await _count(IdempotencyRecord) == 0


# ── 정상 + 캐시 (A4, A5) ──

async def test_A4_새키_1회_생성되고_COMPLETED_저장(client, db):
    ctx = await seed_transaction_context(db)
    resp = await client.post(
        "/transaction/create",
        json=ctx.create_body(),
        headers={**ctx.auth_headers, "Idempotency-Key": "key-a4"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["id"]
    assert await _count(Transaction) == 1
    assert await _count(IdempotencyRecord) == 1

    record = await _fetch_record(IdempotencyRecord)
    assert record.status == "COMPLETED"


async def test_A5_같은키_순차_2회는_캐시응답(client, db):
    ctx = await seed_transaction_context(db)
    headers = {**ctx.auth_headers, "Idempotency-Key": "key-a5"}
    body = ctx.create_body()

    first = await client.post("/transaction/create", json=body, headers=headers)
    second = await client.post("/transaction/create", json=body, headers=headers)

    assert first.status_code == second.status_code == 200
    # 2번째는 라우터 재실행 없이 캐시된 동일 응답
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert await _count(Transaction) == 1


# ── 동시성 (A11) + negative control (A11-nc) ──

@pytest.mark.parametrize("n", [2, 10])
async def test_A11_동시_N발이면_거래_1건만(db, n):
    """같은 user/key/body 로 동시 N발 → ON CONFLICT 락이 1건만 통과시킨다."""
    ctx = await seed_transaction_context(db)

    results = await asyncio.gather(
        *[_post_create(ctx, key="race-key") for _ in range(n)],
        return_exceptions=True,
    )

    assert await _count(Transaction) == 1, f"N={n}: 거래가 1건이어야 함"
    assert await _count(IdempotencyRecord) == 1
    # 응답 분포: 최소 1개는 200(원본 또는 캐시). 나머지는 409(IN_PROGRESS) 또는 200(캐시).
    codes = [r.status_code for r in results if hasattr(r, "status_code")]
    assert 200 in codes, f"N={n}: 성공 응답 하나는 있어야 함 (codes={codes})"


@pytest.mark.parametrize("n", [2, 10])
async def test_A11nc_보호_끄면_동시_N발이_N건_생성(db, n):
    """negative control: Idempotency-Key 없이(보호 끔) 동일 하니스로 N발.

    거래 N건이 생성돼야 A11 의 "1건"이 순차 우연이 아니라 진짜 경합 차단 결과임이
    증명된다. (같은 gather 가 보호 없으면 N건을 만든다.)
    """
    ctx = await seed_transaction_context(db)

    await asyncio.gather(
        *[_post_create(ctx, key=None) for _ in range(n)],
        return_exceptions=True,
    )

    assert await _count(Transaction) == n, f"N={n}: 보호 없으면 N건이어야 함"
    assert await _count(IdempotencyRecord) == 0


# ── 충돌 분기 (A6, A7, A8) ──

async def test_A6_같은키_다른path는_KEY_CONFLICT(client, db):
    ctx = await seed_transaction_context(db)
    key = "key-a6"
    first = await client.post(
        "/transaction/create",
        json=ctx.create_body(),
        headers={**ctx.auth_headers, "Idempotency-Key": key},
    )
    assert first.status_code == 200

    # 같은 (user, key) 인데 path 가 다름 → acquire 단계서 KEY_CONFLICT (라우터 도달 X)
    second = await client.post(
        "/some/other/path",
        json={"x": 1},
        headers={**ctx.auth_headers, "Idempotency-Key": key},
    )
    assert second.status_code == 422
    assert second.json()["code"] == "ID001"


async def test_A7_같은키_다른body는_BODY_MISMATCH(client, db):
    ctx = await seed_transaction_context(db)
    key = "key-a7"
    first = await client.post(
        "/transaction/create",
        json=ctx.create_body(),
        headers={**ctx.auth_headers, "Idempotency-Key": key},
    )
    assert first.status_code == 200

    # 같은 키·같은 path 인데 body(amount) 가 다름 → fingerprint 불일치
    second = await client.post(
        "/transaction/create",
        json=ctx.create_body(amount="2000.00"),
        headers={**ctx.auth_headers, "Idempotency-Key": key},
    )
    assert second.status_code == 422
    assert second.json()["code"] == "ID002"


async def test_A8_PENDING_재진입은_IN_PROGRESS(client, db):
    ctx = await seed_transaction_context(db)
    key = "key-a8"

    # content= 로 raw body 를 직접 통제해 fingerprint 를 정확히 맞춘다
    body_bytes = json.dumps(ctx.create_body()).encode()
    fingerprint = hashlib.sha256(body_bytes).hexdigest()

    # 같은 요청이 처리 중(PENDING)인 상황을 수동으로 심는다
    await db.execute(
        insert(IdempotencyRecord).values(
            id=uuid.uuid4(),
            user_id=ctx.user.id,
            key=key,
            method="POST",
            path="/transaction/create",
            request_fingerprint=fingerprint,
            status="PENDING",
            created_at=datetime.now(),
        ),
    )
    await db.commit()

    resp = await client.post(
        "/transaction/create",
        content=body_bytes,
        headers={
            **ctx.auth_headers,
            "Idempotency-Key": key,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "ID003"


# ── 실패 시 해제 (A9 + A10 통합) ──
# 라우터 예외는 글로벌 Exception 핸들러(ServerErrorMiddleware, 유저 미들웨어보다 바깥)에서
# 잡히므로 IdempotencyMiddleware 의 call_next 는 예외를 raise 로 받아 except 블록(A10 경로)을
# 탄다 → release 후 재-raise → 최종 500. ASGITransport 가 그 예외를 테스트로 전파하지
# 않도록 raise_app_exceptions=False 로 500 응답을 받는다.

async def test_A9_라우터_실패시_PENDING_해제되고_재시도_허용(db, mocker):
    ctx = await seed_transaction_context(db)
    key = "key-a9"

    mocker.patch(
        "app.domain.transaction.service.create_transaction",
        side_effect=RuntimeError("boom"),
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        failed = await c.post(
            "/transaction/create",
            json=ctx.create_body(),
            headers={**ctx.auth_headers, "Idempotency-Key": key},
        )
    assert failed.status_code == 500
    assert await _count(IdempotencyRecord) == 0  # 해제되어 재시도 가능
    assert await _count(Transaction) == 0

    # 같은 키로 재시도 → 이번엔 성공 (캐시된 실패가 없으므로 정상 실행)
    mocker.stopall()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        retried = await c.post(
            "/transaction/create",
            json=ctx.create_body(),
            headers={**ctx.auth_headers, "Idempotency-Key": key},
        )
    assert retried.status_code == 200
    assert await _count(Transaction) == 1


# ── 4xx 캐싱 (A12; codex 발견 — >=500 만 해제, 4xx 는 COMPLETED 로 굳음) ──

async def test_A12_4xx_응답도_캐시된다(client, db):
    ctx = await seed_transaction_context(db)
    # auth_headers 를 미리 고정 (property 재접근으로 인한 lazy load 회피)
    headers = {**ctx.auth_headers, "Idempotency-Key": "key-a12"}

    # 존재하지 않는 category_id → service FK 검증서 NOT_FOUND(400)
    bad_body = ctx.create_body()
    bad_body["categoryId"] = str(uuid.uuid4())

    first = await client.post("/transaction/create", json=bad_body, headers=headers)
    assert first.status_code == 400
    assert await _count(IdempotencyRecord) == 1  # 4xx 도 레코드 저장

    record = await _fetch_record(IdempotencyRecord)
    assert record.status == "COMPLETED"
    assert record.status_code == 400

    # 같은 키·같은 body 재요청 → 캐시된 4xx (재시도로 고칠 수 있는 실패까지 굳는 계약)
    second = await client.post("/transaction/create", json=bad_body, headers=headers)
    assert second.status_code == 400
    assert await _count(Transaction) == 0
