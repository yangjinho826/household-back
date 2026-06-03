from enum import StrEnum


class PortfolioTxType(StrEnum):
    """자산 거래 종류"""

    BUY = "BUY"
    SELL = "SELL"


class AssetClass(StrEnum):
    """자산군 배분 슬라이스 축 — 자산 페이지 배분 파이/추이를 group by 하는 키.

    종목(PortfolioItem)은 분류 없이 전부 INVESTMENT 한 덩어리로 집계한다(채권ETF·
    기타 포함). 실물(COMMODITY=금·원자재)·부동산·연금은 수동자산(ManualAsset)이
    전용계좌로 roll-up 되어 각 슬라이스를 차지한다. CASH 는 현금성 계좌 잔액.
    """

    INVESTMENT = "INVESTMENT"
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
