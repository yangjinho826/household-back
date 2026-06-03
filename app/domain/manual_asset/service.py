import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.domain.account.enum import AccountType
from app.domain.account.model import Account
from app.domain.account.repository import AccountRepository
from app.domain.household.model import Household
from app.domain.manual_asset.model import ManualAsset
from app.domain.manual_asset.repository import ManualAssetRepository
from app.domain.manual_asset.schema import (
    ManualAssetCreateRequest,
    ManualAssetResponse,
    ManualAssetUpdateRequest,
)
from app.domain.portfolio.enum import AssetClass

logger = logging.getLogger(__name__)

# asset_class → 전용 roll-up 계좌 메타 (type, 계좌명, color, icon). 없으면 lazy 생성.
_ROLLUP_ACCOUNT_META: dict[AssetClass, tuple[AccountType, str, str, str]] = {
    AssetClass.REAL_ESTATE: (
        AccountType.REAL_ESTATE, "부동산", "#8B5CF6", "building-estate",
    ),
    AssetClass.PENSION: (
        AccountType.PENSION, "연금", "#EC4899", "pig-money",
    ),
    AssetClass.COMMODITY: (
        AccountType.COMMODITY, "금·원자재", "#F59E0B", "coin",
    ),
}


def _build_response(asset: ManualAsset) -> ManualAssetResponse:
    return ManualAssetResponse(
        id=asset.id,
        account_id=asset.account_id,
        name=asset.name,
        asset_class=AssetClass(asset.asset_class),
        current_valuation=asset.current_valuation,
        valued_at=asset.valued_at,
        is_archived=asset.is_archived,
    )


async def _ensure_rollup_account(
    db: AsyncSession, household: Household, asset_class: AssetClass,
) -> Account:
    """asset_class 전용 roll-up 계좌 — 가계부당 1개. 없으면 생성."""
    account_type, name, color, icon = _ROLLUP_ACCOUNT_META[asset_class]
    repo = AccountRepository(db)
    existing = await repo.search_by_household_id(
        household.id, account_type=account_type.value,
    )
    if existing:
        return existing[0]

    account = Account(
        household_id=household.id,
        name=name,
        account_type=account_type.value,
        start_balance=Decimal("0"),
        color=color,
        icon=icon,
        sort_order=(await repo.max_sort_order(household.id)) + 1,
        is_archived=False,
        data_stat_cd=DataStatus.ACTIVE,
    )
    await repo.save(account)
    logger.info(
        "수동자산 전용계좌 생성 (type=%s, household_id=%s)",
        account_type, household.id,
    )
    return account


async def create(
    db: AsyncSession, household: Household, req: ManualAssetCreateRequest,
) -> ManualAssetResponse:
    if req.account_id is not None:
        account = await AccountRepository(db).find_by_id(req.account_id)
        if not account or account.household_id != household.id:
            raise CustomException(ErrorCode.NOT_FOUND)
        account_id = account.id
    else:
        account = await _ensure_rollup_account(db, household, req.asset_class)
        account_id = account.id

    asset = ManualAsset(
        household_id=household.id,
        account_id=account_id,
        name=req.name.strip(),
        asset_class=req.asset_class.value,
        current_valuation=req.current_valuation,
        valued_at=req.valued_at,
        is_archived=False,
        data_stat_cd=DataStatus.ACTIVE,
    )
    await ManualAssetRepository(db).save(asset)
    logger.info(
        "수동자산 등록 (asset_id=%s, class=%s, valuation=%s)",
        asset.id, asset.asset_class, req.current_valuation,
    )
    return _build_response(asset)


async def update(
    db: AsyncSession, household: Household, asset_id: UUID,
    req: ManualAssetUpdateRequest,
) -> ManualAssetResponse:
    repo = ManualAssetRepository(db)
    asset = await repo.find_by_id(asset_id)
    if not asset or asset.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)

    if req.name is not None:
        asset.name = req.name.strip()
    if req.current_valuation is not None:
        asset.current_valuation = req.current_valuation
    if req.valued_at is not None:
        asset.valued_at = req.valued_at
    if req.is_archived is not None:
        asset.is_archived = req.is_archived
    if req.asset_class is not None and req.asset_class.value != asset.asset_class:
        # 성격 전환 — 전용계좌도 재연결
        asset.asset_class = req.asset_class.value
        account = await _ensure_rollup_account(db, household, req.asset_class)
        asset.account_id = account.id

    await db.flush()
    return _build_response(asset)


async def list_manual_assets(
    db: AsyncSession, household: Household,
) -> list[ManualAssetResponse]:
    assets = await ManualAssetRepository(db).find_active_by_household_id(household.id)
    return [_build_response(a) for a in assets]


async def delete(
    db: AsyncSession, household: Household, asset_id: UUID,
) -> None:
    repo = ManualAssetRepository(db)
    asset = await repo.find_by_id(asset_id)
    if not asset or asset.household_id != household.id:
        raise CustomException(ErrorCode.NOT_FOUND)
    asset.data_stat_cd = DataStatus.DELETED
    await db.flush()
    logger.info("수동자산 삭제 (asset_id=%s)", asset_id)
