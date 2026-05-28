import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.core.pagination import CursorPage
from app.domain.category.enum import CategoryKind
from app.domain.category.model import Category
from app.domain.category.repository import CategoryRepository
from app.domain.category.schema import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
)
from app.domain.household.model import Household

logger = logging.getLogger(__name__)


def _build_response(category: Category) -> CategoryResponse:
    return CategoryResponse(
        id=category.id,
        household_id=category.household_id,
        kind=CategoryKind(category.kind),
        name=category.name,
        color=category.color,
        icon=category.icon,
        sort_order=category.sort_order,
        is_archived=category.is_archived,
    )


async def list_categories(
    db: AsyncSession,
    household: Household,
    *,
    search_term: str | None = None,
    kind: str | None = None,
    is_archived: bool | None = None,
) -> list[CategoryResponse]:
    """내부용 — kind/sort_order 정렬 (transaction form-options 등에서 호출)."""
    repo = CategoryRepository(db)
    categories = await repo.search_by_household_id(
        household.id,
        search_term=search_term,
        kind=kind,
        is_archived=is_archived,
    )
    return [_build_response(c) for c in categories]


async def list_categories_cursor(
    db: AsyncSession,
    household: Household,
    *,
    search_term: str | None = None,
    kind: str | None = None,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 30,
) -> CursorPage[CategoryResponse]:
    """관리 페이지용 — frst_reg_dt DESC 정렬, cursor 무한 스크롤."""
    repo = CategoryRepository(db)
    rows = await repo.list_by_cursor(
        household.id,
        search_term=search_term,
        kind=kind,
        is_archived=is_archived,
        cursor=cursor,
        limit=limit,
    )
    has_next = len(rows) > limit
    rows = rows[:limit]
    items = [_build_response(c) for c in rows]

    total_count = await repo.count_search(
        household.id,
        search_term=search_term,
        kind=kind,
        is_archived=is_archived,
    )

    next_cursor: str | None = None
    if has_next and rows:
        last = rows[-1]
        next_cursor = f"{last.frst_reg_dt.isoformat()}|{last.id}"

    return CursorPage(
        items=items,
        next_cursor=next_cursor,
        has_next=has_next,
        total_count=total_count,
    )


async def create_category(
    db: AsyncSession, household: Household, req: CategoryCreateRequest,
) -> CategoryResponse:
    repo = CategoryRepository(db)
    kind = req.kind
    sort_order = (
        req.sort_order if req.sort_order is not None
        else (await repo.max_sort_order(household.id, kind)) + 1
    )

    category = Category(
        household_id=household.id,
        kind=kind,
        name=req.name.strip(),
        color=req.color,
        icon=req.icon,
        sort_order=sort_order,
        is_archived=False,
        data_stat_cd=DataStatus.ACTIVE,
    )
    await repo.save(category)
    logger.info(
        "카테고리 생성 (category_id=%s, kind=%s, household_id=%s)",
        category.id, kind, household.id,
    )
    return _build_response(category)


async def update_category(
    db: AsyncSession, household: Household, category_id: UUID, req: CategoryUpdateRequest,
) -> CategoryResponse:
    repo = CategoryRepository(db)
    category = await repo.find_by_id(category_id)
    if not category or category.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    if req.kind is not None:
        category.kind = req.kind
    if req.name is not None:
        category.name = req.name.strip()
    if req.color is not None:
        category.color = req.color
    if req.icon is not None:
        category.icon = req.icon
    if req.sort_order is not None:
        category.sort_order = req.sort_order
    if req.is_archived is not None:
        category.is_archived = req.is_archived

    await db.flush()
    return _build_response(category)


async def delete_category(
    db: AsyncSession, household: Household, category_id: UUID,
) -> None:
    repo = CategoryRepository(db)
    category = await repo.find_by_id(category_id)
    if not category or category.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    category.data_stat_cd = DataStatus.DELETED
    await db.flush()
    logger.info("카테고리 삭제 (category_id=%s)", category_id)


async def get_category_detail(
    db: AsyncSession, household: Household, category_id: UUID,
) -> CategoryResponse:
    """카테고리 단건 조회"""
    repo = CategoryRepository(db)
    category = await repo.find_by_id(category_id)
    if not category or category.household_id != household.id or category.data_stat_cd != DataStatus.ACTIVE:
        raise CustomException(ErrorCode.NOT_FOUND)
    return _build_response(category)
