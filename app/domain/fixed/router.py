from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.database import get_db
from app.domain.fixed import service
from app.domain.fixed.schema import (
    FixedCreateRequest,
    FixedResponse,
    FixedUpdateRequest,
)
from app.domain.household.deps import CurrentHousehold

router = APIRouter(prefix="/fixed", tags=["fixed"])


@router.get("/list")
async def list_fixed_expenses(
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[FixedResponse]]:
    """고정지출 참조 목록"""
    response = await service.list_fixed_expenses(db, household)
    return ApiResponse.ok(data=response)


@router.post("/create")
async def create_fixed_expense(
    req: FixedCreateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FixedResponse]:
    """고정지출 생성"""
    response = await service.create_fixed_expense(db, household, req)
    return ApiResponse.ok(data=response)


@router.put("/update/{fixed_id}")
async def update_fixed_expense(
    fixed_id: UUID,
    req: FixedUpdateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FixedResponse]:
    """고정지출 수정"""
    response = await service.update_fixed_expense(db, household, fixed_id, req)
    return ApiResponse.ok(data=response)


@router.delete("/delete/{fixed_id}")
async def delete_fixed_expense(
    fixed_id: UUID,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """고정지출 삭제 (soft)"""
    await service.delete_fixed_expense(db, household, fixed_id)
    return ApiResponse.ok()
