from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.types import Money, Rate
from app.domain.account.enum import AccountType


class AccountCreateRequest(BaseModel):
    name: str
    account_type: AccountType
    start_balance: Decimal = Decimal("0")
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None

    @model_validator(mode="after")
    def _validate(self) -> "AccountCreateRequest":
        if not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.color is not None and len(self.color) > 7:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class AccountUpdateRequest(BaseModel):
    name: str | None = None
    account_type: AccountType | None = None
    start_balance: Decimal | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None
    is_archived: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> "AccountUpdateRequest":
        if self.name is not None and not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.color is not None and len(self.color) > 7:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class AccountResponse(BaseModel):
    id: UUID
    household_id: UUID
    name: str
    account_type: AccountType
    start_balance: Money
    balance: Money
    color: str | None
    icon: str | None
    sort_order: int
    is_archived: bool

    # INVESTMENT 통장 전용 (LIVING/SAVINGS 는 None)
    cash: Money | None = None
    portfolio_cost: Money | None = None
    portfolio_valuation: Money | None = None
    portfolio_profit_loss: Money | None = None
    portfolio_profit_loss_rate: Rate | None = None

    model_config = {"from_attributes": True}
