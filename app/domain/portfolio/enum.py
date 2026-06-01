from enum import StrEnum


class PortfolioTxType(StrEnum):
    """자산 거래 종류"""

    BUY = "BUY"
    SELL = "SELL"


class AssetClass(StrEnum):
    """자산 성격 — market(거래소)과 직교하는 축.

    market 은 "어디서 거래되나", asset_class 는 "무엇이냐". 금을 KRX_KOSPI 에
    욱여넣던 문제를 해소한다 — 금ETF·금현물 모두 COMMODITY, 주식ETF(KODEX200)는
    STOCK, 채권ETF는 BOND. 배분 파이는 이 축으로 group by 한다.
    ETF/현물은 wrapper(형태)일 뿐 asset_class 가 아니다 — 담은 내용물 성격으로 분류.
    """

    STOCK = "STOCK"
    BOND = "BOND"
    COMMODITY = "COMMODITY"
    CASH = "CASH"
    REAL_ESTATE = "REAL_ESTATE"
    PENSION = "PENSION"
    OTHER = "OTHER"


class Market(StrEnum):
    """종목 시장 — Yahoo 심볼 접미사 1:1 매핑.

    KRX_KOSPI/KRX_KOSDAQ 은 한국, NASDAQ/NYSE 는 미국.
    OTHER 는 야후 미지원 (금시세/원자재/채권 등) — 야후 호출 절대 X, 가격 수동 입력.
    USD 환산 분기 등은 country_code 프로퍼티로 도출.
    """

    KRX_KOSPI = "KRX_KOSPI"
    KRX_KOSDAQ = "KRX_KOSDAQ"
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    OTHER = "OTHER"

    @property
    def yahoo_suffix(self) -> str:
        """Yahoo ticker 접미사. 미국은 빈 문자열. OTHER 접근 시 KeyError — invariant."""
        return {
            Market.KRX_KOSPI: ".KS",
            Market.KRX_KOSDAQ: ".KQ",
            Market.NASDAQ: "",
            Market.NYSE: "",
        }[self]

    @property
    def country_code(self) -> str:
        """그룹핑/표시용 — KR or US 도출. OTHER 는 정의되지 않음."""
        if self in (Market.KRX_KOSPI, Market.KRX_KOSDAQ):
            return "KR"
        if self in (Market.NASDAQ, Market.NYSE):
            return "US"
        raise ValueError(f"country_code is undefined for {self}")
