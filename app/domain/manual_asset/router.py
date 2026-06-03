from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.database import get_db
from app.domain.household.deps import CurrentHousehold
from app.domain.manual_asset import service
from app.domain.manual_asset.schema import (
    ManualAssetCreateRequest,
    ManualAssetResponse,
    ManualAssetUpdateRequest,
)

router = APIRouter(prefix="/manual-asset", tags=["manual-asset"])


@router.get("/list")
async def list_manual_assets(
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ManualAssetResponse]]:
    """수동자산(부동산·연금) 전체 목록"""
    response = await service.list_manual_assets(db, household)
    return ApiResponse.ok(data=response)


@router.post("/create")
async def create_manual_asset(
    req: ManualAssetCreateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ManualAssetResponse]:
    """부동산·연금 등록 — account_id 미지정 시 전용계좌 자동 연결"""
    response = await service.create(db, household, req)
    return ApiResponse.ok(data=response)


@router.put("/{asset_id}")
async def update_manual_asset(
    asset_id: UUID,
    req: ManualAssetUpdateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ManualAssetResponse]:
    """평가액/메타 수정"""
    response = await service.update(db, household, asset_id, req)
    return ApiResponse.ok(data=response)


@router.delete("/{asset_id}")
async def delete_manual_asset(
    asset_id: UUID,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """수동자산 soft delete"""
    await service.delete(db, household, asset_id)
    return ApiResponse.ok()
