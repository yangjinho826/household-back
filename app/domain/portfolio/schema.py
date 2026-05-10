from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.domain.portfolio.enum import PortfolioTxType


class PortfolioCreateRequest(BaseModel):
    """매수 요청"""

    ticker: str
    symbol: str | None = None
    quantity: Decimal
    price: Decimal
    account_id: UUID
    tx_date: date | None = None
    memo: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "PortfolioCreateRequest":
        if not (1 <= len(self.ticker.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.quantity <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.price <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class PortfolioUpdateRequest(BaseModel):
    """평가액/메타 수정 (transaction 무관)"""

    current_price: Decimal | None = None
    ticker: str | None = None
    symbol: str | None = None
    is_archived: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> "PortfolioUpdateRequest":
        if self.current_price is not None and self.current_price < 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.ticker is not None and not (1 <= len(self.ticker.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class PortfolioSellRequest(BaseModel):
    """매도 요청 (부분/전량)"""

    quantity: Decimal
    sell_price: Decimal
    tx_date: date | None = None
    memo: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "PortfolioSellRequest":
        if self.quantity <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.sell_price <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class PortfolioResponse(BaseModel):
    """보유 종목 응답 (PNL 포함)"""

    id: UUID
    account_id: UUID
    account_name: str
    ticker: str
    symbol: str | None
    quantity: Decimal
    avg_price: Decimal
    current_price: Decimal
    cost: Decimal
    valuation: Decimal
    profit_loss: Decimal
    profit_loss_rate: Decimal
    is_archived: bool


class PortfolioTxResponse(BaseModel):
    """매수/매도 이력 응답"""

    id: UUID
    account_id: UUID
    account_name: str
    ticker: str
    symbol: str | None
    pt_type: PortfolioTxType
    quantity: Decimal
    price: Decimal
    total: Decimal
    tx_date: date
    memo: str | None
