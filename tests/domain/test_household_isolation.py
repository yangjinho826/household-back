"""D3. 가계부 격리 (IDOR) — 명세 기반 사후검증.

**공개계약**
- `get_current_household`(`household/deps.py:18-33`) — `X-Household-Id` 헤더 → 멤버십 검증 →
  멤버가 아니면 `HOUSEHOLD_NOT_MEMBER`
- 각 도메인 서비스는 리소스를 꺼낸 뒤 `household_id != household.id` 면 `NOT_FOUND`
  (`transaction/service.py:182,199,213` 등)
- `get_current_user`(`core/auth/deps.py:32`) — 토큰 `type` 이 ACCESS 가 아니면 `INVALID_TOKEN`

**왜 이 축의 우선순위를 낮췄나**: 착수 전 `app/domain/*/service.py` 의 public 함수를
전수 스캔해 "`find_by_id` 로 리소스를 꺼낸 뒤 소속 검증이 없는 곳"을 찾았고 **0건**이었다.
예외는 `user` 도메인(`detail_user`/`search_by_email`)뿐인데 이건 멤버 초대용 설계 선택이다
(라우터에 "인증 가드용" 주석 명시). 그래서 결함 발견이 아니라 **회귀 안전망**이 목적이다 —
소속 검증은 중앙화돼 있지 않고 각 서비스 함수가 개별로 하므로, 새 엔드포인트가 빠뜨리기 쉽다.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.core.auth.jwt import create_refresh_token
from app.core.exceptions import CustomException, ErrorCode
from app.domain.transaction import service
from app.domain.transaction.enum import TxType
from app.domain.transaction.schema import (
    TransactionCreateRequest,
    TransactionUpdateRequest,
)
from tests.fixtures.factory import seed_transaction_context, token_for


@pytest_asyncio.fixture
async def two_households(db):
    """서로 다른 유저·가계부 2세트. HTTP 경유 케이스가 있어 commit 까지 한다."""
    alice = await seed_transaction_context(db)
    bob = await seed_transaction_context(db)
    return alice, bob


async def _create_tx(db, ctx, *, amount: str = "1000"):
    return await service.create_transaction(
        db,
        ctx.household,
        TransactionCreateRequest(
            txType=TxType.EXPENSE,
            amount=Decimal(amount),
            txDate=date(2026, 1, 15),
            accountId=ctx.account.id,
            categoryId=ctx.category.id,
        ),
        ctx.user,
    )


async def test_D3_1_타_가계부_거래는_조회되지_않는다(db, two_households):
    # given: bob 의 가계부에 거래 1건
    alice, bob = two_households
    bob_tx = await _create_tx(db, bob)

    # when / then: alice 의 가계부 컨텍스트로는 안 보인다
    with pytest.raises(CustomException) as exc:
        await service.get_transaction_detail(db, alice.household, bob_tx.id)
    assert exc.value.error_code == ErrorCode.NOT_FOUND


async def test_D3_2_타_가계부_거래는_수정되지_않는다(db, two_households):
    # given
    alice, bob = two_households
    bob_tx = await _create_tx(db, bob, amount="1000")

    # when / then
    with pytest.raises(CustomException) as exc:
        await service.update_transaction(
            db, alice.household, bob_tx.id,
            TransactionUpdateRequest(amount=Decimal("99999")),
        )
    assert exc.value.error_code == ErrorCode.NOT_FOUND

    # then: 원본이 그대로여야 한다
    intact = await service.get_transaction_detail(db, bob.household, bob_tx.id)
    assert intact.amount == Decimal("1000")


async def test_D3_3_타_가계부_거래는_삭제되지_않는다(db, two_households):
    # given
    alice, bob = two_households
    bob_tx = await _create_tx(db, bob)

    # when / then
    with pytest.raises(CustomException) as exc:
        await service.delete_transaction(db, alice.household, bob_tx.id)
    assert exc.value.error_code == ErrorCode.NOT_FOUND

    # then: 살아있어야 한다
    assert await service.get_transaction_detail(db, bob.household, bob_tx.id)


async def test_D3_4_멤버가_아닌_가계부_ID로는_접근이_차단된다(db, two_households, client):
    """`X-Household-Id` 만 바꿔치기하는 경로 — 멤버십 검증이 막아야 한다."""
    alice, bob = two_households

    # when: alice 토큰 + bob 의 household id
    response = await client.get(
        "/transaction/form-options",
        headers={
            "Authorization": f"Bearer {token_for(alice.user)}",
            "X-Household-Id": str(bob.household.id),
        },
    )

    # then
    assert response.status_code == ErrorCode.HOUSEHOLD_NOT_MEMBER.status
    assert response.json()["code"] == ErrorCode.HOUSEHOLD_NOT_MEMBER.code


async def test_D3_5_refresh_토큰으로는_보호_API에_접근할_수_없다(db, two_households, client):
    """토큰 타입 오용 — refresh 는 재발급 전용이라 ACCESS 자리에 못 쓴다."""
    alice, _ = two_households
    refresh = create_refresh_token({"sub": str(alice.user.id)})

    # when
    response = await client.get(
        "/transaction/form-options",
        headers={
            "Authorization": f"Bearer {refresh}",
            "X-Household-Id": str(alice.household.id),
        },
    )

    # then
    assert response.status_code == ErrorCode.INVALID_TOKEN.status
    assert response.json()["code"] == ErrorCode.INVALID_TOKEN.code
