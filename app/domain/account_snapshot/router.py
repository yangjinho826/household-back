from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.database import get_db
from app.domain.account_snapshot import service
from app.domain.account_snapshot.schema import SnapshotMonth, SnapshotYearlyResponse
from app.domain.household.deps import CurrentHousehold

router = APIRouter(prefix="/account-snapshot", tags=["account-snapshot"])


@router.post("/create")
async def create_snapshot(
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SnapshotMonth]:
    """이번 달 자산 스냅샷 (모든 active 통장 일괄)"""
    response = await service.create_current_month_snapshot(db, household)
    return ApiResponse.ok(data=response)


@router.get("/yearly")
async def yearly_snapshots(
    household: CurrentHousehold,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SnapshotYearlyResponse]:
    """월별 자산 추이 (기본 최근 12개월)"""
    response = await service.get_yearly_snapshots(db, household, from_date, to_date)
    return ApiResponse.ok(data=response)
