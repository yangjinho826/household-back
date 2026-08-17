from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.pagination import CursorPage
from app.core.schema import CamelBaseModel
from app.core.types import Money, Quantity, Rate
from app.domain.account.schema import AccountResponse
from app.domain.portfolio.enum import Market, PortfolioTxType


class PortfolioRefreshResponse(CamelBaseModel):
    """수동 시세 갱신 결과 — 갱신/실패 종목 수 + 영향받은 row 수."""

    fetched: int
    skipped: int
    updated_rows: int


class PortfolioValueHistoryByAccountQuery(CamelBaseModel):
    """통장 단위 종목별 평가액 추이 쿼리. accountId 필수, 기간 옵션."""

    account_id: UUID
    from_date: date | None = None
    to_date: date | None = None


class PortfolioValueHistoryByItemQuery(CamelBaseModel):
    """종목 단위 평가액 추이 쿼리. 기간 옵션."""

    from_date: date | None = None
    to_date: date | None = None


class PortfolioCreateRequest(CamelBaseModel):
    """종목 등록 — 메타만 (수량/매수가는 매수 액션에서)"""

    name: str
    code: str = ""
    market: Market
    current_price: Decimal
    account_id: UUID

    @model_validator(mode="after")
    def _validate(self) -> "PortfolioCreateRequest":
        if not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        # OTHER (야후 미지원) 면 code 빈문자열 허용, 그 외엔 1~50 필수
        if self.market != Market.OTHER:
            if not (1 <= len(self.code.strip()) <= 50):
                raise CustomException(ErrorCode.BAD_REQUEST)
        if self.current_price <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class PortfolioLookupResponse(CamelBaseModel):
    """야후 파이낸스 종목 조회 결과 — 폼 자동 채움용"""

    market: Market
    code: str
    name: str
    current_price: Money
    yahoo_symbol: str


class PortfolioBuyRequest(CamelBaseModel):
    """매수 액션 — qty 누적 + avg_price 재계산 + 이력 기록.

    fee 는 매수원가에 가산돼 평단을 올린다(증권사 계산과 동일).
    """

    quantity: Decimal
    price: Decimal
    fee: Decimal = Decimal("0")
    tx_date: date | None = None
    memo: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "PortfolioBuyRequest":
        if self.quantity <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.price <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.fee < 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class PortfolioUpdateRequest(CamelBaseModel):
    """평가액/메타 수정 (transaction 무관)"""

    current_price: Decimal | None = None
    name: str | None = None
    code: str | None = None
    market: Market | None = None
    is_archived: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> "PortfolioUpdateRequest":
        if self.current_price is not None and self.current_price < 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.name is not None and not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        # OTHER 종목 수정 케이스 대비 — code 빈문자열 허용, max 50 만 강제
        if self.code is not None and len(self.code.strip()) > 50:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class PortfolioSellRequest(CamelBaseModel):
    """매도 요청 (부분/전량). fee 는 실현손익에서 차감된다."""

    quantity: Decimal
    sell_price: Decimal
    fee: Decimal = Decimal("0")
    tx_date: date | None = None
    memo: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "PortfolioSellRequest":
        if self.quantity <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.sell_price <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.fee < 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class PortfolioTxUpdateRequest(CamelBaseModel):
    """거래 내역 수정 — pt_type 은 변경 불가 (매수↔매도 전환은 별도 거래로)"""

    quantity: Decimal | None = None
    price: Decimal | None = None
    fee: Decimal | None = None
    tx_date: date | None = None
    memo: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "PortfolioTxUpdateRequest":
        if self.quantity is not None and self.quantity <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.price is not None and self.price <= 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.fee is not None and self.fee < 0:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class PortfolioResponse(CamelBaseModel):
    """보유 종목 응답 (PNL 포함)"""

    id: UUID
    account_id: UUID
    account_name: str
    name: str
    code: str
    market: Market
    quantity: Quantity
    avg_price: Money
    current_price: Money
    cost: Money
    valuation: Money
    profit_loss: Money
    profit_loss_rate: Rate
    is_archived: bool


class PortfolioTxResponse(CamelBaseModel):
    """매수/매도 이력 응답"""

    id: UUID
    account_id: UUID
    account_name: str
    name: str
    code: str
    market: Market
    pt_type: PortfolioTxType
    quantity: Quantity
    price: Money
    # total 은 거래금액(gross, 수량×단가), settlement_amount 는 정산금액(net).
    # 증권사 거래내역이 둘 다 보여주므로 어느 하나로 대체하지 않는다.
    total: Money
    fee: Money
    settlement_amount: Money
    tx_date: date
    memo: str | None
    # 매도 실현손익 — SELL 만 값, BUY/미집계는 null
    realized_pnl: Money | None = None


class RealizedPnlRow(CamelBaseModel):
    """매매손익 — 매도 1건 (증권사 '매매손익' 테이블 행)"""

    tx_id: UUID
    tx_date: date
    name: str | None = None  # 계좌 단위 응답에서 종목명 (종목 단위 응답은 None)
    quantity: Quantity
    sell_price: Money
    amount: Money  # 거래금액 (gross) = 수량 × 단가
    fee: Money
    settlement: Money  # 정산금액 = 거래금액 − 수수료
    realized_pnl: Money
    realized_rate: Rate


class RealizedPnlSummary(CamelBaseModel):
    """매매손익 요약 — 기간 내 매도 전체 합산.

    sell_amount/buy_amount 는 gross, total_realized 는 수수료 차감 후 net 이라
    한 화면에 gross 와 net 이 섞인다. total_fee 를 따로 두어 그 차이를 드러낸다
    (증권사 매매손익 화면의 '제비용'과 같은 역할).
    """

    total_realized: Money
    total_rate: Rate
    sell_amount: Money
    buy_amount: Money
    total_fee: Money


class RealizedPnlResponse(CamelBaseModel):
    """종목 매매손익 응답 — 요약 + 매도 건별.

    effective_from/to 는 실제 적용된 조회 기간. from 미지정 시 백엔드가
    '최근 1년 ↔ 첫 매도일' 중 더 이른 쪽으로 확장하므로, 프론트가 이 값으로
    날짜 입력을 채운다(기본 범위가 첫 매도를 놓치지 않게).
    """

    summary: RealizedPnlSummary
    rows: list[RealizedPnlRow]
    effective_from: date
    effective_to: date


class PortfolioValueHistoryPoint(CamelBaseModel):
    """월별 박제 데이터 1건"""

    snapshot_date: date
    quantity: Quantity
    avg_price: Money
    current_price: Money
    cost: Money
    valuation: Money


class PortfolioValueHistoryByItem(CamelBaseModel):
    """종목별 그루핑 — 차트의 라인 1개에 해당"""

    portfolio_item_id: UUID
    account_id: UUID
    name: str
    code: str
    market: Market
    history: list[PortfolioValueHistoryPoint]


# =========================================================
# Page-level overview responses (페이지 진입 시 1호출)
# =========================================================


class PortfolioOverviewSummary(CamelBaseModel):
    """포트폴리오 메인 hero — 전체 투자 계좌 합산"""

    total_balance: Money
    total_cash: Money
    total_valuation: Money
    total_cost: Money
    total_profit: Money
    total_rate: Rate


class InvestmentAccountWithPortfolios(CamelBaseModel):
    """투자 계좌 1건 + 그 계좌의 보유 종목 묶음"""

    account: AccountResponse
    portfolios: list[PortfolioResponse]


class PortfolioOverviewResponse(CamelBaseModel):
    """포트폴리오 메인 페이지 진입 응답 — account + portfolio 한 번에"""

    summary: PortfolioOverviewSummary
    investment_accounts: list[InvestmentAccountWithPortfolios]


class AccountOverviewResponse(CamelBaseModel):
    """계좌 상세 페이지 진입 응답.

    INVESTMENT 통장은 portfolios 가 채워지고, 그 외 타입은 빈 리스트.
    """

    account: AccountResponse
    portfolios: list[PortfolioResponse]


class PortfolioFormOptionsResponse(CamelBaseModel):
    """종목 등록/수정 폼 옵션 — INVESTMENT 계좌 옵션만"""

    investment_accounts: list[AccountResponse]


# 종목 단건 거래 내역 — 커서 무한 스크롤
PortfolioTxPage = CursorPage[PortfolioTxResponse]
