from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.types import Money


def _check_common(name: str | None, amount: Decimal | None, day_of_month: int | None, color: str | None) -> None:
    if name is not None and not (1 <= len(name.strip()) <= 100):
        raise CustomException(ErrorCode.BAD_REQUEST)
    if amount is not None and amount <= 0:
        raise CustomException(ErrorCode.BAD_REQUEST)
    if day_of_month is not None and not (1 <= day_of_month <= 31):
        raise CustomException(ErrorCode.BAD_REQUEST)
    if color is not None and len(color) > 7:
        raise CustomException(ErrorCode.BAD_REQUEST)


class FixedCreateRequest(BaseModel):
    name: str
    amount: Decimal
    day_of_month: int
    category_id: UUID | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None

    @model_validator(mode="after")
    def _validate(self) -> "FixedCreateRequest":
        _check_common(self.name, self.amount, self.day_of_month, self.color)
        return self


class FixedUpdateRequest(BaseModel):
    name: str | None = None
    amount: Decimal | None = None
    day_of_month: int | None = None
    category_id: UUID | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None
    is_archived: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> "FixedUpdateRequest":
        _check_common(self.name, self.amount, self.day_of_month, self.color)
        return self


class FixedResponse(BaseModel):
    id: UUID
    household_id: UUID
    name: str
    amount: Money
    day_of_month: int
    category_id: UUID | None
    category_name: str | None
    category_color: str | None
    category_icon: str | None
    color: str | None
    icon: str | None
    sort_order: int
    is_archived: bool


class FixedMonthlyUsage(BaseModel):
    fixed_expense_id: UUID
    used: Money


class FixedMonthlySummaryResponse(BaseModel):
    month: str  # YYYY-MM
    items: list[FixedMonthlyUsage]
