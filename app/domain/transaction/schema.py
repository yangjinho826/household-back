from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.types import Money
from app.domain.transaction.enum import TxType


class TransactionCreateRequest(BaseModel):
    tx_type: TxType
    amount: Decimal
    tx_date: date
    account_id: UUID
    to_account_id: UUID | None = None
    category_id: UUID | None = None
    paid_by_user_id: UUID | None = None
    fixed_expense_id: UUID | None = None
    memo: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "TransactionCreateRequest":
        if self.amount <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.tx_type == TxType.TRANSFER:
            if self.to_account_id is None:
                raise CustomException(ErrorCode.BAD_REQUEST)
            if self.to_account_id == self.account_id:
                raise CustomException(ErrorCode.BAD_REQUEST)
            if self.category_id is not None:
                raise CustomException(ErrorCode.BAD_REQUEST)
            if self.fixed_expense_id is not None:
                raise CustomException(ErrorCode.BAD_REQUEST)
        else:
            if self.to_account_id is not None:
                raise CustomException(ErrorCode.BAD_REQUEST)
        # 고정 지출 매핑은 expense 만
        if self.fixed_expense_id is not None and self.tx_type != TxType.EXPENSE:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class TransactionUpdateRequest(BaseModel):
    tx_type: TxType | None = None
    amount: Decimal | None = None
    tx_date: date | None = None
    account_id: UUID | None = None
    to_account_id: UUID | None = None
    category_id: UUID | None = None
    paid_by_user_id: UUID | None = None
    fixed_expense_id: UUID | None = None
    memo: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "TransactionUpdateRequest":
        if self.amount is not None and self.amount <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if (
            self.account_id is not None
            and self.to_account_id is not None
            and self.account_id == self.to_account_id
        ):
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class TransactionResponse(BaseModel):
    id: UUID
    household_id: UUID
    tx_type: TxType
    amount: Money
    tx_date: date
    account_id: UUID
    account_name: str | None
    to_account_id: UUID | None
    to_account_name: str | None
    category_id: UUID | None
    category_name: str | None
    category_color: str | None
    category_icon: str | None
    paid_by_user_id: UUID | None
    fixed_expense_id: UUID | None
    memo: str | None


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    next_cursor: str | None
    has_next: bool
    total_count: int


class CalendarDay(BaseModel):
    date: date
    income: Money
    expense: Money
    transfer: Money
    count: int


class CalendarResponse(BaseModel):
    year: int
    month: int
    monthly_income: Money
    monthly_expense: Money
    monthly_transfer: Money
    days: list[CalendarDay]
