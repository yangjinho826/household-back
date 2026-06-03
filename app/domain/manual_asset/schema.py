from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.schema import CamelBaseModel
from app.core.types import Money
from app.domain.portfolio.enum import AssetClass

# 수동자산이 가질 수 있는 자산 성격 — 종목(INVESTMENT)과 구분되는 실물·부동산·연금
_MANUAL_ASSET_CLASSES = {
    AssetClass.REAL_ESTATE,
    AssetClass.PENSION,
    AssetClass.COMMODITY,
}


class ManualAssetCreateRequest(CamelBaseModel):
    """부동산·연금 등록. account_id 미지정 시 asset_class 전용계좌 자동 연결."""

    name: str
    asset_class: AssetClass
    current_valuation: Decimal
    valued_at: date
    account_id: UUID | None = None

    @model_validator(mode="after")
    def _validate(self) -> "ManualAssetCreateRequest":
        if not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.asset_class not in _MANUAL_ASSET_CLASSES:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.current_valuation <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class ManualAssetUpdateRequest(CamelBaseModel):
    """평가액/메타 수정. asset_class 변경 시 전용계좌도 재연결(service)."""

    name: str | None = None
    asset_class: AssetClass | None = None
    current_valuation: Decimal | None = None
    valued_at: date | None = None
    is_archived: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> "ManualAssetUpdateRequest":
        if self.name is not None and not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        if (
            self.asset_class is not None
            and self.asset_class not in _MANUAL_ASSET_CLASSES
        ):
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.current_valuation is not None and self.current_valuation <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class ManualAssetResponse(CamelBaseModel):
    id: UUID
    account_id: UUID
    name: str
    asset_class: AssetClass
    current_valuation: Money
    valued_at: date
    is_archived: bool
