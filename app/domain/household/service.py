import logging
from datetime import datetime, date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.domain.household.enum import HouseholdRole
from app.domain.household.model import Household, HouseholdMember
from app.domain.household.repository import (
    HouseholdMemberRepository,
    HouseholdRepository,
)
from app.domain.household.schema import (
    HouseholdCreateRequest,
    HouseholdResponse,
    HouseholdUpdateRequest,
)
from app.domain.user.model import User

logger = logging.getLogger(__name__)


def _build_response(household: Household, role: HouseholdRole) -> HouseholdResponse:
    return HouseholdResponse(
        id=household.id,
        name=household.name,
        description=household.description,
        owner_id=household.owner_id,
        currency=household.currency,
        started_at=household.started_at,
        role=role,
    )


async def list_households(db: AsyncSession, current_user: User) -> list[HouseholdResponse]:
    """현재 user 가 멤버인 가계부 목록"""
    repo = HouseholdRepository(db)
    households = await repo.find_active_by_user_id(current_user.id)
    return [
        _build_response(
            h,
            HouseholdRole.OWNER if h.owner_id == current_user.id else HouseholdRole.MEMBER,
        )
        for h in households
    ]


async def create_household(
    db: AsyncSession, req: HouseholdCreateRequest, current_user: User,
) -> HouseholdResponse:
    """가계부 생성 + owner 멤버 row 자동 등록"""
    household_repo = HouseholdRepository(db)
    member_repo = HouseholdMemberRepository(db)

    household = Household(
        name=req.name.strip(),
        description=req.description,
        owner_id=current_user.id,
        currency=req.currency.upper(),
        started_at=req.started_at or date.today(),
        data_stat_cd=DataStatus.ACTIVE,
    )
    await household_repo.save(household)

    owner_member = HouseholdMember(
        household_id=household.id,
        user_id=current_user.id,
        role=HouseholdRole.OWNER,
        joined_at=datetime.now(),
        data_stat_cd=DataStatus.ACTIVE,
    )
    await member_repo.save(owner_member)

    logger.info("가계부 생성 (household_id=%s, owner_id=%s)", household.id, current_user.id)
    return _build_response(household, HouseholdRole.OWNER)


async def update_household(
    db: AsyncSession,
    household_id: UUID,
    req: HouseholdUpdateRequest,
    current_user: User,
) -> HouseholdResponse:
    """가계부 수정 (owner 만)"""
    repo = HouseholdRepository(db)
    household = await repo.find_by_id(household_id)
    if not household:
        raise CustomException(ErrorCode.HOUSEHOLD_NOT_FOUND)
    if household.owner_id != current_user.id:
        raise CustomException(ErrorCode.HOUSEHOLD_NOT_OWNER)

    if req.name is not None:
        household.name = req.name.strip()
    if req.description is not None:
        household.description = req.description
    if req.currency is not None:
        household.currency = req.currency.upper()
    if req.started_at is not None:
        household.started_at = req.started_at

    await db.flush()
    return _build_response(household, HouseholdRole.OWNER)


async def delete_household(
    db: AsyncSession, household_id: UUID, current_user: User,
) -> None:
    """가계부 soft delete (owner 만)"""
    repo = HouseholdRepository(db)
    household = await repo.find_by_id(household_id)
    if not household:
        raise CustomException(ErrorCode.HOUSEHOLD_NOT_FOUND)
    if household.owner_id != current_user.id:
        raise CustomException(ErrorCode.HOUSEHOLD_NOT_OWNER)

    household.data_stat_cd = DataStatus.DELETED
    await db.flush()
    logger.info("가계부 삭제 (household_id=%s)", household_id)
