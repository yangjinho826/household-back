from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.auth.deps import CurrentUser
from app.core.database import get_db
from app.domain.household.deps import CurrentHousehold
from app.domain.transaction import service
from app.domain.transaction.enum import TxType
from app.domain.transaction.repository import TransactionFilter
from app.domain.transaction.schema import (
    CalendarResponse,
    TransactionCreateRequest,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdateRequest,
)

router = APIRouter(prefix="/transaction", tags=["transaction"])


@router.get("/list")
async def list_transactions(
    household: CurrentHousehold,
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=500),
    tx_type: TxType | None = Query(None),
    account_id: UUID | None = Query(None),
    category_id: UUID | None = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TransactionListResponse]:
    """거래 목록 (커서 기반 페이징)"""
    f = TransactionFilter(
        tx_type=tx_type,
        account_id=account_id,
        category_id=category_id,
        year=year,
        month=month,
        from_date=from_date,
        to_date=to_date,
    )
    response = await service.list_transactions(db, household, f, cursor, limit)
    return ApiResponse.ok(data=response)


@router.post("/create")
async def create_transaction(
    req: TransactionCreateRequest,
    household: CurrentHousehold,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TransactionResponse]:
    """거래 생성"""
    response = await service.create_transaction(db, household, req, current_user)
    return ApiResponse.ok(data=response)


@router.put("/update/{tx_id}")
async def update_transaction(
    tx_id: UUID,
    req: TransactionUpdateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TransactionResponse]:
    """거래 수정"""
    response = await service.update_transaction(db, household, tx_id, req)
    return ApiResponse.ok(data=response)


@router.delete("/delete/{tx_id}")
async def delete_transaction(
    tx_id: UUID,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """거래 삭제 (soft)"""
    await service.delete_transaction(db, household, tx_id)
    return ApiResponse.ok()


@router.get("/detail/{tx_id}")
async def get_transaction_detail(
    tx_id: UUID,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TransactionResponse]:
    """거래 단건 조회"""
    response = await service.get_transaction_detail(db, household, tx_id)
    return ApiResponse.ok(data=response)


@router.get("/calendar")
async def get_calendar(
    household: CurrentHousehold,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CalendarResponse]:
    """달력 뷰 — 일별 income/expense/transfer 합계 + 월간 합계"""
    response = await service.get_calendar(db, household, year, month)
    return ApiResponse.ok(data=response)
