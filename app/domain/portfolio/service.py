import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.domain.account.enum import AccountType
from app.domain.account.repository import AccountRepository
from app.domain.household.model import Household
from app.domain.portfolio.enum import PortfolioTxType
from app.domain.portfolio.model import (
    PortfolioItem,
    PortfolioTransaction,
    PortfolioValueHistory,
)
from app.domain.portfolio.repository import (
    PortfolioItemRepository,
    PortfolioTransactionRepository,
    PortfolioValueHistoryRepository,
)
from app.domain.portfolio.schema import (
    PortfolioBuyRequest,
    PortfolioCreateRequest,
    PortfolioResponse,
    PortfolioSellRequest,
    PortfolioTxResponse,
    PortfolioUpdateRequest,
    PortfolioValueHistoryByItem,
    PortfolioValueHistoryPoint,
)

logger = logging.getLogger(__name__)


def _build_response(item: PortfolioItem, account_map: dict) -> PortfolioResponse:
    account = account_map.get(item.account_id)
    cost = item.quantity * item.avg_price
    valuation = item.quantity * item.current_price
    profit_loss = valuation - cost
    profit_loss_rate = (profit_loss / cost * Decimal("100")) if cost > 0 else Decimal("0.00")

    return PortfolioResponse(
        id=item.id,
        account_id=item.account_id,
        account_name=account.name if account else "(삭제됨)",
        ticker=item.ticker,
        symbol=item.symbol,
        quantity=item.quantity,
        avg_price=item.avg_price,
        current_price=item.current_price,
        cost=cost,
        valuation=valuation,
        profit_loss=profit_loss,
        profit_loss_rate=profit_loss_rate,
        is_archived=item.is_archived,
    )


def _build_tx_response(tx: PortfolioTransaction, account_map: dict) -> PortfolioTxResponse:
    account = account_map.get(tx.account_id)
    return PortfolioTxResponse(
        id=tx.id,
        account_id=tx.account_id,
        account_name=account.name if account else "(삭제됨)",
        ticker=tx.ticker,
        symbol=tx.symbol,
        pt_type=tx.pt_type,
        quantity=tx.quantity,
        price=tx.price,
        total=tx.quantity * tx.price,
        tx_date=tx.tx_date,
        memo=tx.memo,
    )


async def _validate_investment_account(
    db: AsyncSession, household_id: UUID, account_id: UUID,
):
    """INVESTMENT 통장이고 같은 가계부 소속인지 검증"""
    accounts = await AccountRepository(db).find_by_ids([account_id])
    if not accounts:
        raise CustomException(ErrorCode.NOT_FOUND)
    a = accounts[0]
    if a.household_id != household_id or a.data_stat_cd != DataStatus.ACTIVE:
        raise CustomException(ErrorCode.NOT_FOUND)
    if a.account_type != AccountType.INVESTMENT:
        raise CustomException(ErrorCode.BAD_REQUEST)
    return a


async def list_portfolio(
    db: AsyncSession, household: Household, account_id: UUID | None = None,
) -> list[PortfolioResponse]:
    """보유 종목 목록 (옵션: account_id 필터)"""
    repo = PortfolioItemRepository(db)
    if account_id:
        items = await repo.find_active_by_account_id(account_id)
        items = [i for i in items if i.household_id == household.id]
    else:
        items = await repo.find_active_by_household_id(household.id)

    account_ids = list({i.account_id for i in items})
    accounts = await AccountRepository(db).find_by_ids(account_ids)
    account_map = {a.id: a for a in accounts}

    return [_build_response(i, account_map) for i in items]


async def create_portfolio(
    db: AsyncSession, household: Household, req: PortfolioCreateRequest,
) -> PortfolioResponse:
    """종목 등록 — 메타만 (qty=0, avg_price=0). 매수는 buy() 로"""
    await _validate_investment_account(db, household.id, req.account_id)

    item = PortfolioItem(
        household_id=household.id,
        account_id=req.account_id,
        ticker=req.ticker.strip(),
        symbol=req.symbol,
        quantity=Decimal("0.0000"),
        avg_price=Decimal("0.00"),
        current_price=req.current_price,
        is_archived=False,
        data_stat_cd=DataStatus.ACTIVE,
    )
    await PortfolioItemRepository(db).save(item)
    logger.info(
        "종목 등록 (account_id=%s, ticker=%s, current_price=%s)",
        req.account_id, item.ticker, req.current_price,
    )

    accounts = await AccountRepository(db).find_by_ids([item.account_id])
    return _build_response(item, {a.id: a for a in accounts})


async def buy(
    db: AsyncSession, household: Household, item_id: UUID, req: PortfolioBuyRequest,
) -> PortfolioResponse:
    """매수 액션 — qty 누적 + avg_price 재계산 + 이력 기록"""
    item_repo = PortfolioItemRepository(db)
    pt_repo = PortfolioTransactionRepository(db)

    item = await item_repo.find_by_id(item_id)
    if not item or item.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    # 1. 매수 이력 기록
    pt_tx = PortfolioTransaction(
        household_id=household.id,
        account_id=item.account_id,
        portfolio_item_id=item.id,
        ticker=item.ticker,
        symbol=item.symbol,
        pt_type=PortfolioTxType.BUY,
        quantity=req.quantity,
        price=req.price,
        tx_date=req.tx_date or date.today(),
        memo=req.memo,
        data_stat_cd=DataStatus.ACTIVE,
    )
    await pt_repo.save(pt_tx)

    # 2. 누적 평균단가 재계산
    if item.quantity == 0:
        item.avg_price = req.price
    else:
        item.avg_price = (
            item.quantity * item.avg_price + req.quantity * req.price
        ) / (item.quantity + req.quantity)
    item.quantity += req.quantity
    await db.flush()

    logger.info(
        "매수 (item_id=%s, qty=%s, price=%s, total_qty=%s, avg=%s)",
        item.id, req.quantity, req.price, item.quantity, item.avg_price,
    )

    accounts = await AccountRepository(db).find_by_ids([item.account_id])
    return _build_response(item, {a.id: a for a in accounts})


async def update_portfolio(
    db: AsyncSession, household: Household, item_id: UUID, req: PortfolioUpdateRequest,
) -> PortfolioResponse:
    """평가액/메타 수정 (transaction 무관)"""
    repo = PortfolioItemRepository(db)
    item = await repo.find_by_id(item_id)
    if not item or item.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    if req.current_price is not None:
        item.current_price = req.current_price
    if req.ticker is not None:
        item.ticker = req.ticker.strip()
    if req.symbol is not None:
        item.symbol = req.symbol
    if req.is_archived is not None:
        item.is_archived = req.is_archived

    await db.flush()

    accounts = await AccountRepository(db).find_by_ids([item.account_id])
    return _build_response(item, {a.id: a for a in accounts})


async def sell(
    db: AsyncSession, household: Household, item_id: UUID, req: PortfolioSellRequest,
) -> PortfolioResponse | None:
    """매도 (부분/전량). 전량 시 portfolio_items soft delete, 응답 None"""
    item_repo = PortfolioItemRepository(db)
    pt_repo = PortfolioTransactionRepository(db)

    item = await item_repo.find_by_id(item_id)
    if not item or item.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    if req.quantity > item.quantity:
        raise CustomException(ErrorCode.BAD_REQUEST)

    # 매도 이력 기록
    pt_tx = PortfolioTransaction(
        household_id=household.id,
        account_id=item.account_id,
        portfolio_item_id=item.id,
        ticker=item.ticker,
        symbol=item.symbol,
        pt_type=PortfolioTxType.SELL,
        quantity=req.quantity,
        price=req.sell_price,
        tx_date=req.tx_date or date.today(),
        memo=req.memo,
        data_stat_cd=DataStatus.ACTIVE,
    )
    await pt_repo.save(pt_tx)

    # 보유량 차감
    remaining = item.quantity - req.quantity
    if remaining == 0:
        item.data_stat_cd = DataStatus.DELETED
        await db.flush()
        logger.info("전량 매도 (item_id=%s, qty=%s)", item.id, req.quantity)
        return None

    item.quantity = remaining
    await db.flush()
    logger.info(
        "부분 매도 (item_id=%s, sold=%s, remaining=%s)",
        item.id, req.quantity, remaining,
    )

    accounts = await AccountRepository(db).find_by_ids([item.account_id])
    return _build_response(item, {a.id: a for a in accounts})


async def list_portfolio_transactions(
    db: AsyncSession, household: Household, account_id: UUID | None = None,
) -> list[PortfolioTxResponse]:
    """매수/매도 이력 조회"""
    repo = PortfolioTransactionRepository(db)
    if account_id:
        rows = await repo.find_active_by_account_id(account_id)
        rows = [r for r in rows if r.household_id == household.id]
    else:
        rows = await repo.find_active_by_household_id(household.id)

    account_ids = list({r.account_id for r in rows})
    accounts = await AccountRepository(db).find_by_ids(account_ids)
    account_map = {a.id: a for a in accounts}

    return [_build_tx_response(r, account_map) for r in rows]


async def delete_portfolio(
    db: AsyncSession, household: Household, item_id: UUID,
) -> None:
    """종목 soft delete (data_stat_cd='99'). value_history row 는 보존"""
    repo = PortfolioItemRepository(db)
    item = await repo.find_by_id(item_id)
    if not item or item.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)
    item.data_stat_cd = DataStatus.DELETED
    await db.flush()
    logger.info("종목 삭제 (item_id=%s)", item_id)


async def get_portfolio_detail(
    db: AsyncSession, household: Household, item_id: UUID,
) -> PortfolioResponse:
    """종목 단건 조회 — PNL 포함"""
    repo = PortfolioItemRepository(db)
    item = await repo.find_by_id(item_id)
    if not item or item.household_id != household.id or item.data_stat_cd != DataStatus.ACTIVE:
        raise CustomException(ErrorCode.NOT_FOUND)
    accounts = await AccountRepository(db).find_by_ids([item.account_id])
    return _build_response(item, {a.id: a for a in accounts})


def _default_date_range(
    from_date: date | None, to_date: date | None,
) -> tuple[date, date]:
    """기본: 최근 12개월 — account-snapshot/yearly 와 동일 컨벤션"""
    today = date.today().replace(day=1)
    if not to_date:
        to_date = today
    else:
        to_date = to_date.replace(day=1)
    if not from_date:
        total = to_date.year * 12 + (to_date.month - 1) - 11
        y, m = divmod(total, 12)
        from_date = date(y, m + 1, 1)
    else:
        from_date = from_date.replace(day=1)
    return from_date, to_date


def _to_history_point(row: PortfolioValueHistory) -> PortfolioValueHistoryPoint:
    return PortfolioValueHistoryPoint(
        snapshot_date=row.snapshot_date,
        quantity=row.quantity,
        avg_price=row.avg_price,
        current_price=row.current_price,
        cost=row.cost,
        valuation=row.valuation,
    )


async def get_value_history_by_account(
    db: AsyncSession,
    household: Household,
    account_id: UUID,
    from_date: date | None,
    to_date: date | None,
) -> list[PortfolioValueHistoryByItem]:
    """통장 단위 — 종목별 그루핑된 월별 평가액 추이"""
    accounts = await AccountRepository(db).find_by_ids([account_id])
    if not accounts or accounts[0].household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    from_date, to_date = _default_date_range(from_date, to_date)

    history_repo = PortfolioValueHistoryRepository(db)
    rows = await history_repo.find_by_account_and_range(account_id, from_date, to_date)

    if not rows:
        return []

    # 삭제된 종목도 ticker 표시 위해 직접 fetch
    item_ids = list({r.portfolio_item_id for r in rows})
    items = await PortfolioItemRepository(db).find_by_ids_including_deleted(item_ids)
    item_map = {i.id: i for i in items}

    grouped: dict[UUID, list[PortfolioValueHistory]] = {}
    for r in rows:
        grouped.setdefault(r.portfolio_item_id, []).append(r)

    return [
        PortfolioValueHistoryByItem(
            portfolio_item_id=item_id,
            account_id=account_id,
            ticker=item_map[item_id].ticker if item_id in item_map else "(삭제됨)",
            symbol=item_map[item_id].symbol if item_id in item_map else None,
            history=[_to_history_point(p) for p in points],
        )
        for item_id, points in grouped.items()
    ]


async def get_value_history_by_item(
    db: AsyncSession,
    household: Household,
    item_id: UUID,
    from_date: date | None,
    to_date: date | None,
) -> PortfolioValueHistoryByItem:
    """특정 종목 — 월별 평가액 추이 (삭제된 종목도 조회 가능)"""
    items = await PortfolioItemRepository(db).find_by_ids_including_deleted([item_id])
    if not items or items[0].household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)
    item = items[0]

    from_date, to_date = _default_date_range(from_date, to_date)

    history_repo = PortfolioValueHistoryRepository(db)
    rows = await history_repo.find_by_item_and_range(item_id, from_date, to_date)

    return PortfolioValueHistoryByItem(
        portfolio_item_id=item.id,
        account_id=item.account_id,
        ticker=item.ticker,
        symbol=item.symbol,
        history=[_to_history_point(r) for r in rows],
    )
