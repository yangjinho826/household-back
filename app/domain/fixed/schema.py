from uuid import UUID

from pydantic import model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.schema import CamelBaseModel
from app.core.types import Money


def _check_common(name: str | None, day_of_month: int | None, color: str | None) -> None:
    if name is not None and not (1 <= len(name.strip()) <= 100):
        raise CustomException(ErrorCode.BAD_REQUEST)
    if day_of_month is not None and not (1 <= day_of_month <= 31):
        raise CustomException(ErrorCode.BAD_REQUEST)
    if color is not None and len(color) > 7:
        raise CustomException(ErrorCode.BAD_REQUEST)


class FixedCreateRequest(CamelBaseModel):
    name: str
    day_of_month: int
    category_id: UUID | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None

    @model_validator(mode="after")
    def _validate(self) -> "FixedCreateRequest":
        _check_common(self.name, self.day_of_month, self.color)
        return self


class FixedUpdateRequest(CamelBaseModel):
    name: str | None = None
    day_of_month: int | None = None
    category_id: UUID | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None
    is_archived: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> "FixedUpdateRequest":
        _check_common(self.name, self.day_of_month, self.color)
        return self


class FixedResponse(CamelBaseModel):
    id: UUID
    household_id: UUID
    name: str
    day_of_month: int
    category_id: UUID | None
    category_name: str | None
    category_color: str | None
    category_icon: str | None
    color: str | None
    icon: str | None
    sort_order: int
    is_archived: bool


class FixedMonthlyUsage(CamelBaseModel):
    fixed_expense_id: UUID
    used: Money


class FixedMonthlySummaryResponse(CamelBaseModel):
    month: str  # YYYY-MM
    items: list[FixedMonthlyUsage]
