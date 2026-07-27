"""테스트 데이터 팩토리.

각 factory 는 flush 까지만(같은 세션 내 가시성). 반면 동시성 테스트(A11)는
미들웨어·라우터가 각자 독립 async_session 을 쓰므로 flush 만으로는 다른 커넥션에서
안 보인다 → seed_transaction_context 가 마지막에 commit 까지 책임진다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.jwt import create_access_token
from app.core.enums.data_status import DataStatus
from app.domain.account.enum import AccountType
from app.domain.account.model import Account
from app.domain.category.enum import CategoryKind
from app.domain.category.model import Category
from app.domain.household.enum import HouseholdRole
from app.domain.household.model import Household, HouseholdMember
from app.domain.user.model import User


async def user_factory(db: AsyncSession, *, email: str | None = None, name: str = "테스터") -> User:
    user = User(
        email=email or f"user-{uuid.uuid4().hex[:8]}@test.com",
        name=name,
        password_hash="x",  # 로그인 대신 token_for 로 토큰 직접 발급 — 해시 불필요
        language="ko",
        data_stat_cd=DataStatus.ACTIVE,
    )
    db.add(user)
    await db.flush()
    return user


async def household_factory(db: AsyncSession, *, owner: User, name: str = "테스트 가계부") -> Household:
    household = Household(
        name=name,
        owner_id=owner.id,
        currency="KRW",
        started_at=date(2026, 1, 1),
        data_stat_cd=DataStatus.ACTIVE,
    )
    db.add(household)
    await db.flush()
    return household


async def member_factory(
    db: AsyncSession, *, household: Household, user: User, role: str = HouseholdRole.OWNER,
) -> HouseholdMember:
    member = HouseholdMember(
        household_id=household.id,
        user_id=user.id,
        role=role,
        joined_at=datetime.now(),
        data_stat_cd=DataStatus.ACTIVE,
    )
    db.add(member)
    await db.flush()
    return member


async def account_factory(
    db: AsyncSession,
    *,
    household: Household,
    name: str = "생활비 통장",
    account_type: str = AccountType.LIVING,
    start_balance: Decimal = Decimal("0"),
) -> Account:
    account = Account(
        household_id=household.id,
        name=name,
        account_type=account_type,
        start_balance=start_balance,
        sort_order=0,
        is_archived=False,
        data_stat_cd=DataStatus.ACTIVE,
    )
    db.add(account)
    await db.flush()
    return account


async def category_factory(
    db: AsyncSession,
    *,
    household: Household,
    kind: str = CategoryKind.EXPENSE,
    name: str = "식비",
) -> Category:
    category = Category(
        household_id=household.id,
        kind=kind,
        name=name,
        sort_order=0,
        is_archived=False,
        data_stat_cd=DataStatus.ACTIVE,
    )
    db.add(category)
    await db.flush()
    return category


def token_for(user: User) -> str:
    """로그인 흐름 우회 — user.id 를 sub 로 access token 직접 발급."""
    return create_access_token({"sub": str(user.id)})


@dataclass
class TxContext:
    """멱등성 실증(POST /transaction/create)에 필요한 최소 셋업 묶음."""

    user: User
    household: Household
    account: Account
    category: Category

    @property
    def auth_headers(self) -> dict[str, str]:
        """Bearer + X-Household-Id. Idempotency-Key 는 각 테스트가 붙인다."""
        return {
            "Authorization": f"Bearer {token_for(self.user)}",
            "X-Household-Id": str(self.household.id),
        }

    def create_body(self, *, amount: str = "1000.00", tx_date: str = "2026-01-15") -> dict:
        """유효한 EXPENSE 거래 생성 요청 body (camelCase alias)."""
        return {
            "txType": "EXPENSE",
            "amount": amount,
            "txDate": tx_date,
            "accountId": str(self.account.id),
            "categoryId": str(self.category.id),
        }


async def seed_transaction_context(db: AsyncSession) -> TxContext:
    """user→household→membership→account→category 를 심고 **commit**.

    commit 이 필수인 이유: 동시성 테스트는 요청마다 독립 커넥션이라
    커밋 안 된 데이터는 다른 세션에서 안 보인다. 매 테스트 후 conftest 의
    TRUNCATE 가 정리하므로 commit 해도 격리는 유지된다.
    """
    user = await user_factory(db)
    household = await household_factory(db, owner=user)
    await member_factory(db, household=household, user=user)
    account = await account_factory(db, household=household)
    category = await category_factory(db, household=household)
    await db.commit()
    return TxContext(user=user, household=household, account=account, category=category)
