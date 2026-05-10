from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.auth.deps import CurrentUser
from app.core.database import get_db
from app.domain.household import service
from app.domain.household.schema import (
    HouseholdCreateRequest,
    HouseholdResponse,
    HouseholdUpdateRequest,
)

router = APIRouter(prefix="/household", tags=["household"])


@router.get("/list")
async def list_households(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[HouseholdResponse]]:
    """현재 user 가 멤버인 가계부 목록"""
    response = await service.list_households(db, current_user)
    return ApiResponse.ok(data=response)


@router.post("/create")
async def create_household(
    req: HouseholdCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[HouseholdResponse]:
    """가계부 생성 (생성자가 owner 로 자동 등록)"""
    response = await service.create_household(db, req, current_user)
    return ApiResponse.ok(data=response)


@router.put("/update/{household_id}")
async def update_household(
    household_id: UUID,
    req: HouseholdUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[HouseholdResponse]:
    """가계부 수정 (owner 만)"""
    response = await service.update_household(db, household_id, req, current_user)
    return ApiResponse.ok(data=response)


@router.delete("/delete/{household_id}")
async def delete_household(
    household_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """가계부 삭제 (soft, owner 만)"""
    await service.delete_household(db, household_id, current_user)
    return ApiResponse.ok()
