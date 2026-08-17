from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.pagination import CursorPage
from app.core.schema import CamelBaseModel
from app.core.types import Money
from app.domain.account.schema import AccountResponse
from app.domain.category.schema import CategoryResponse
from app.domain.fixed.schema import FixedResponse
from app.domain.stats.schema import CategoryStatsItem
from app.domain.transaction.enum import TxType, ValuationDirection


class TransactionListQuery(CamelBaseModel):
    """거래 목록 쿼리 파라미터. CamelBaseModel 이라 camelCase 자동 매핑.

    cursor / limit 도 같은 모델 안에 두는 이유:
    fastapi 의 Annotated[Model, Query()] 패턴은 같은 시그니처에 별도 Query 파라미터가
    공존하면 모델 unwrap 을 못해 모델 자체를 단일 query 로 처리 → 400 발생.
    페이징 파라미터까지 한 모델에 묶어 시그니처에 모델 1개만 남겨야 정상 분해됨.
    """

    cursor: str | None = None
    limit: int = Field(20, ge=1, le=500)
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
    # 평가조정(VALUATION) 거래의 증감 방향 — VALUATION 일 때만 허용/필수.
    valuation_direction: ValuationDirection | None = None

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
        # 평가조정(VALUATION): 방향 필수 + category 금지 (to_account/fixed 는 위 else 에서 금지됨).
        if self.tx_type == TxType.VALUATION:
            if self.valuation_direction is None:
                raise CustomException(ErrorCode.BAD_REQUEST)
            if self.category_id is not None:
                raise CustomException(ErrorCode.BAD_REQUEST)
        elif self.valuation_direction is not None:
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
    valuation_direction: ValuationDirection | None = None

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
    # 보관/삭제된 고정지출에 물린 과거 거래도 이름이 채워진다 (FixedRepository.find_by_ids)
    fixed_expense_name: str | None
    valuation_direction: ValuationDirection | None
    memo: str | None


TransactionListResponse = CursorPage[TransactionResponse]


class AccountLedgerItem(TransactionResponse):
    """계좌 거래 이력 행 — 거래 응답 + 그 계좌 관점의 부호 금액 + 거래 후 잔액.

    signed_amount: 이 계좌 기준 +(입금/수입)/−(출금/지출). 이체는 양쪽 계좌에서 부호 다름.
    balance_after: 그 거래 직후 이 계좌의 현금흐름 잔액(running balance).
    """

    signed_amount: Money
    balance_after: Money


AccountLedgerPage = CursorPage[AccountLedgerItem]


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


class CalendarFullResponse(CamelBaseModel):
    """달력 페이지 진입 1호출 — 일별 합계 + 카테고리별 stats + 그달 거래.

    캘린더 UI 가 필요한 모든 데이터를 한 번에. by_category 는 차트/카드 확장 여지.
    """

    year: int
    month: int
    monthly_income: Money
    monthly_expense: Money
    monthly_transfer: Money
    days: list[CalendarDay]
    by_category: list[CategoryStatsItem]
    transactions: list[TransactionResponse]


class TransactionFormOptionsResponse(CamelBaseModel):
    """거래 등록/수정 폼 옵션 — 통장 + 카테고리 + 활성 고정지출"""

    accounts: list[AccountResponse]
    categories: list[CategoryResponse]
    fixed_expenses: list[FixedResponse]
