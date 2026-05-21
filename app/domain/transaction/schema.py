from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.schema import CamelBaseModel
from app.core.types import Money
from app.domain.transaction.enum import TxType


class TransactionListQuery(CamelBaseModel):
    """거래 목록 쿼리 파라미터. CamelBaseModel 이라 camelCase 자동 매핑."""

    tx_type: TxType | None = None
    account_id: UUID | None = None
    category_id: UUID | None = None
    year: int | None = Field(None, ge=2000, le=2100)
    month: int | None = Field(None, ge=1, le=12)
    from_date: date | None = None
    to_date: date | None = None


class TransactionCreateRequest(CamelBaseModel):
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
        # FIXED_EXPENSE 는 fixed_expense_id 필수. 그 외 유형은 매핑 금지.
        if self.tx_type == TxType.FIXED_EXPENSE:
            if self.fixed_expense_id is None:
                raise CustomException(ErrorCode.BAD_REQUEST)
        else:
            if self.fixed_expense_id is not None:
                raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class TransactionUpdateRequest(CamelBaseModel):
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


class TransactionResponse(CamelBaseModel):
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


class TransactionListResponse(CamelBaseModel):
    """거래 목록 — 커서 기반 페이징.

    다른 도메인은 단순 list[Response] 를 반환 (전체 조회 + 프론트에서 wrap).
    transaction 만 데이터량이 많아 커서 페이징 적용.
    프론트는 nextCursor 가 null 아닐 때까지 추가 fetch.
    """

    items: list[TransactionResponse]
    next_cursor: str | None
    has_next: bool
    total_count: int


class CalendarDay(CamelBaseModel):
    date: date
    income: Money
    expense: Money
    transfer: Money
    count: int


class CalendarResponse(CamelBaseModel):
    year: int
    month: int
    monthly_income: Money
    monthly_expense: Money
    monthly_transfer: Money
    days: list[CalendarDay]
