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


@dataclass
class LedgerContext:
    """계좌 원장 테스트용 셋업 — 거래통장 2개(이체용) + 수동자산 통장(평가조정용)."""

    user: User
    household: Household
    account: Account
    other_account: Account
    manual_asset: Account
    expense_category: Category
    income_category: Category


async def seed_ledger_context(
    db: AsyncSession, *, start_balance: Decimal = Decimal("0"),
) -> LedgerContext:
    """user→household→membership→통장 3종→카테고리 2종. flush 까지만.

    통장이 3개인 이유: 이체는 출발/도착 두 계좌가 필요하고(D1-4), 평가조정은
    수동자산 통장에만 허용되기 때문(_validate_fk_belong_to_household).
    카테고리도 2종 — 지출 거래엔 EXPENSE, 수입 거래엔 INCOME kind 만 통과한다.
    """
    user = await user_factory(db)
    household = await household_factory(db, owner=user)
    await member_factory(db, household=household, user=user)
    account = await account_factory(db, household=household, start_balance=start_balance)
    other_account = await account_factory(db, household=household, name="비상금 통장")
    manual_asset = await account_factory(
        db, household=household, name="아파트", account_type=AccountType.REAL_ESTATE,
    )
    expense_category = await category_factory(db, household=household)
    income_category = await category_factory(
        db, household=household, kind=CategoryKind.INCOME, name="급여",
    )
    return LedgerContext(
        user=user,
        household=household,
        account=account,
        other_account=other_account,
        manual_asset=manual_asset,
        expense_category=expense_category,
        income_category=income_category,
    )


@dataclass
class PortfolioContext:
    """포트폴리오 도메인 테스트용 셋업 — INVESTMENT 통장까지."""

    user: User
    household: Household
    account: Account


async def seed_portfolio_context(db: AsyncSession) -> PortfolioContext:
    """user→household→membership→INVESTMENT 통장. flush 까지만.

    포트폴리오 손익 테스트는 단일 세션에서 서비스 함수를 직접 호출하므로
    seed_transaction_context 와 달리 commit 이 불필요하다(동시성 없음).
    """
    user = await user_factory(db)
    household = await household_factory(db, owner=user)
    await member_factory(db, household=household, user=user)
    account = await account_factory(
        db, household=household, name="증권 계좌", account_type=AccountType.INVESTMENT,
    )
    return PortfolioContext(user=user, household=household, account=account)


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
