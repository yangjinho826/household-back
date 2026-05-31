from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.schema import CamelBaseModel
from app.core.types import Money, Rate
from app.domain.account.enum import AccountType


class AccountListQuery(CamelBaseModel):
    """통장 목록 쿼리 파라미터 (cursor 무한 스크롤).

    cursor / limit 도 같은 모델 안에 둠 — transaction 과 동일 이유 (fastapi
    Annotated[Model, Query()] 패턴은 별도 Query 파라미터가 공존하면 모델 unwrap 실패).
    """

    cursor: str | None = None
    limit: int = Field(30, ge=1, le=200)
    search_term: str | None = None
    account_type: AccountType | None = None
    is_archived: bool | None = None


class AccountCreateRequest(CamelBaseModel):
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


class AccountUpdateRequest(CamelBaseModel):
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


class AccountResponse(CamelBaseModel):
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


class AccountMonthlyFlow(CamelBaseModel):
    """계좌별 리포트의 월 1행 — 그달 수입/지출 흐름 + 잔액."""

    month_date: date  # 그달 1일
    income: Money
    expense: Money
    fixed_expense: Money
    balance: Money  # 그달 박제 잔액 (이번달은 현재 잔액)


class AccountReportResponse(CamelBaseModel):
    """계좌별 리포트 — 현재 잔액 + 월별 수입/지출 추이.

    monthly_flows 는 박제된 과거 월 + 아직 박제 전인 이번달(실시간 집계)을 합친 것.
    """

    account_id: UUID
    account_name: str
    account_type: AccountType
    balance: Money
    monthly_flows: list[AccountMonthlyFlow]
