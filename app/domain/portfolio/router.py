from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.database import get_db
from app.domain.household.deps import CurrentHousehold
from app.domain.portfolio import service
from app.domain.portfolio.schema import (
    PortfolioBuyRequest,
    PortfolioCreateRequest,
    PortfolioResponse,
    PortfolioSellRequest,
    PortfolioTxResponse,
    PortfolioUpdateRequest,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/list")
async def list_portfolio(
    household: CurrentHousehold,
    account_id: UUID | None = Query(None, alias="accountId"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[PortfolioResponse]]:
    """보유 종목 목록 (PNL 포함). accountId 옵션 — 통장별 필터"""
    response = await service.list_portfolio(db, household, account_id)
    return ApiResponse.ok(data=response)


@router.post("/create")
async def create_portfolio(
    req: PortfolioCreateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PortfolioResponse]:
    """종목 등록 — 메타만 (qty=0 시작). 매수는 /buy/{id}"""
    response = await service.create_portfolio(db, household, req)
    return ApiResponse.ok(data=response)


@router.post("/buy/{item_id}")
async def buy_portfolio(
    item_id: UUID,
    req: PortfolioBuyRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PortfolioResponse]:
    """매수 — qty 누적 + avg_price 재계산 + 이력 기록"""
    response = await service.buy(db, household, item_id, req)
    return ApiResponse.ok(data=response)


@router.put("/update/{item_id}")
async def update_portfolio(
    item_id: UUID,
    req: PortfolioUpdateRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PortfolioResponse]:
    """평가액/메타 수정 (transaction 무관)"""
    response = await service.update_portfolio(db, household, item_id, req)
    return ApiResponse.ok(data=response)


@router.post("/sell/{item_id}")
async def sell_portfolio(
    item_id: UUID,
    req: PortfolioSellRequest,
    household: CurrentHousehold,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PortfolioResponse | None]:
    """매도 (부분/전량). 전량 시 응답 data=null"""
    response = await service.sell(db, household, item_id, req)
    return ApiResponse.ok(data=response)


@router.get("/transactions")
async def list_portfolio_transactions(
    household: CurrentHousehold,
    account_id: UUID | None = Query(None, alias="accountId"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[PortfolioTxResponse]]:
    """매수/매도 이력"""
    response = await service.list_portfolio_transactions(db, household, account_id)
    return ApiResponse.ok(data=response)
