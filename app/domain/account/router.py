from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.database import get_db
from app.domain.account import service
from app.domain.account.enum import AccountType
from app.domain.account.schema import (
    AccountCreateRequest,
    AccountResponse,
    AccountUpdateRequest,
)
from app.domain.household.deps import CurrentHousehold

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/list")
async def list_accounts(
    household: CurrentHousehold,
    search_term: str | None = Query(None, alias="searchTerm"),
    account_type: AccountType | None = Query(None, alias="accountType"),
    is_archived: bool | None = Query(None, alias="isArchived"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AccountResponse]]:
    """통장 목록 — searchTerm/accountType/isArchived 필터"""
    response = await service.list_accounts(
        db, household,
        search_term=search_term,
        account_type=account_type.value if account_type else None,
        is_archived=is_archived,
    )
    return ApiResponse.ok(data=response)


@router.post("/create")
async def create_account(
    req: AccountCreateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AccountResponse]:
    """통장 생성"""
    response = await service.create_account(db, household, req)
    return ApiResponse.ok(data=response)


@router.get("/detail/{account_id}")
async def get_account_detail(
    account_id: UUID,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AccountResponse]:
    """통장 단건 조회"""
    response = await service.get_account_detail(db, household, account_id)
    return ApiResponse.ok(data=response)


@router.put("/update/{account_id}")
async def update_account(
    account_id: UUID,
    req: AccountUpdateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AccountResponse]:
    """통장 수정"""
    response = await service.update_account(db, household, account_id, req)
    return ApiResponse.ok(data=response)


@router.delete("/delete/{account_id}")
async def delete_account(
    account_id: UUID,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """통장 삭제 (soft)"""
    await service.delete_account(db, household, account_id)
    return ApiResponse.ok()
