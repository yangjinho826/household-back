from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.database import get_db
from app.domain.household.deps import CurrentHousehold
from app.domain.stats import service
from app.domain.stats.schema import MonthlyStatsResponse

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/monthly")
async def get_monthly_stats(
    household: CurrentHousehold,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[MonthlyStatsResponse]:
    """월간 카테고리별 지출/수입 집계 — 이번 달 지출 카드/차트용"""
    response = await service.get_monthly_stats(db, household, year, month)
    return ApiResponse.ok(data=response)
