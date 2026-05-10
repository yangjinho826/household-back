import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.domain.category.repository import CategoryRepository
from app.domain.fixed.model import FixedExpense
from app.domain.fixed.repository import FixedRepository
from app.domain.fixed.schema import (
    FixedCreateRequest,
    FixedResponse,
    FixedUpdateRequest,
)
from app.domain.household.model import Household

logger = logging.getLogger(__name__)


def _build_response(fixed: FixedExpense, category_map: dict) -> FixedResponse:
    category = category_map.get(fixed.category_id) if fixed.category_id else None
    return FixedResponse(
        id=fixed.id,
        household_id=fixed.household_id,
        name=fixed.name,
        amount=fixed.amount,
        day_of_month=fixed.day_of_month,
        category_id=fixed.category_id,
        category_name=category.name if category else None,
        category_color=category.color if category else None,
        category_icon=category.icon if category else None,
        color=fixed.color,
        icon=fixed.icon,
        sort_order=fixed.sort_order,
        is_archived=fixed.is_archived,
    )


async def _validate_category(
    db: AsyncSession, household_id: UUID, category_id: UUID,
) -> None:
    """category_id 가 같은 household 의 active 카테고리인지 검증"""
    categories = await CategoryRepository(db).find_by_ids([category_id])
    if not categories:
        raise CustomException(ErrorCode.NOT_FOUND)
    c = categories[0]
    if c.household_id != household_id or c.data_stat_cd != DataStatus.ACTIVE:
        raise CustomException(ErrorCode.NOT_FOUND)


async def list_fixed_expenses(
    db: AsyncSession, household: Household,
) -> list[FixedResponse]:
    repo = FixedRepository(db)
    rows = await repo.find_active_by_household_id(household.id)

    category_ids = [r.category_id for r in rows if r.category_id]
    categories = await CategoryRepository(db).find_by_ids(category_ids)
    category_map = {c.id: c for c in categories}

    return [_build_response(r, category_map) for r in rows]


async def create_fixed_expense(
    db: AsyncSession, household: Household, req: FixedCreateRequest,
) -> FixedResponse:
    if req.category_id is not None:
        await _validate_category(db, household.id, req.category_id)

    repo = FixedRepository(db)
    sort_order = (
        req.sort_order if req.sort_order is not None
        else (await repo.max_sort_order(household.id)) + 1
    )

    fixed = FixedExpense(
        household_id=household.id,
        name=req.name.strip(),
        amount=req.amount,
        day_of_month=req.day_of_month,
        category_id=req.category_id,
        color=req.color,
        icon=req.icon,
        sort_order=sort_order,
        is_archived=False,
        data_stat_cd=DataStatus.ACTIVE,
    )
    await repo.save(fixed)
    logger.info("고정지출 생성 (fixed_id=%s, household_id=%s)", fixed.id, household.id)

    category_map = {}
    if req.category_id:
        cats = await CategoryRepository(db).find_by_ids([req.category_id])
        category_map = {c.id: c for c in cats}
    return _build_response(fixed, category_map)


async def update_fixed_expense(
    db: AsyncSession, household: Household, fixed_id: UUID, req: FixedUpdateRequest,
) -> FixedResponse:
    repo = FixedRepository(db)
    fixed = await repo.find_by_id(fixed_id)
    if not fixed or fixed.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    if req.category_id is not None:
        await _validate_category(db, household.id, req.category_id)

    if req.name is not None:
        fixed.name = req.name.strip()
    if req.amount is not None:
        fixed.amount = req.amount
    if req.day_of_month is not None:
        fixed.day_of_month = req.day_of_month
    if req.category_id is not None:
        fixed.category_id = req.category_id
    if req.color is not None:
        fixed.color = req.color
    if req.icon is not None:
        fixed.icon = req.icon
    if req.sort_order is not None:
        fixed.sort_order = req.sort_order
    if req.is_archived is not None:
        fixed.is_archived = req.is_archived

    await db.flush()

    category_map = {}
    if fixed.category_id:
        cats = await CategoryRepository(db).find_by_ids([fixed.category_id])
        category_map = {c.id: c for c in cats}
    return _build_response(fixed, category_map)


async def delete_fixed_expense(
    db: AsyncSession, household: Household, fixed_id: UUID,
) -> None:
    repo = FixedRepository(db)
    fixed = await repo.find_by_id(fixed_id)
    if not fixed or fixed.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    fixed.data_stat_cd = DataStatus.DELETED
    await db.flush()
    logger.info("고정지출 삭제 (fixed_id=%s)", fixed_id)
