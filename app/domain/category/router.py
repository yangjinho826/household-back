from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.database import get_db
from app.domain.category import service
from app.domain.category.enum import CategoryKind
from app.domain.category.schema import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
)
from app.domain.household.deps import CurrentHousehold

router = APIRouter(prefix="/category", tags=["category"])


@router.get("/list")
async def list_categories(
    household: CurrentHousehold,
    search_term: str | None = Query(None, alias="searchTerm"),
    kind: CategoryKind | None = Query(None),
    is_archived: bool | None = Query(None, alias="isArchived"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[CategoryResponse]]:
    """카테고리 목록 — searchTerm/kind/isArchived 필터"""
    response = await service.list_categories(
        db, household,
        search_term=search_term,
        kind=kind.value if kind else None,
        is_archived=is_archived,
    )
    return ApiResponse.ok(data=response)


@router.post("/create")
async def create_category(
    req: CategoryCreateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CategoryResponse]:
    """카테고리 생성"""
    response = await service.create_category(db, household, req)
    return ApiResponse.ok(data=response)


@router.get("/detail/{category_id}")
async def get_category_detail(
    category_id: UUID,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CategoryResponse]:
    """카테고리 단건 조회"""
    response = await service.get_category_detail(db, household, category_id)
    return ApiResponse.ok(data=response)


@router.put("/update/{category_id}")
async def update_category(
    category_id: UUID,
    req: CategoryUpdateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CategoryResponse]:
    """카테고리 수정"""
    response = await service.update_category(db, household, category_id, req)
    return ApiResponse.ok(data=response)


@router.delete("/delete/{category_id}")
async def delete_category(
    category_id: UUID,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """카테고리 삭제 (soft)"""
    await service.delete_category(db, household, category_id)
    return ApiResponse.ok()
