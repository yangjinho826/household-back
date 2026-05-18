from enum import StrEnum


class PortfolioTxType(StrEnum):
    """자산 거래 종류"""

    BUY = "BUY"
    SELL = "SELL"


class Market(StrEnum):
    """종목 시장 — Yahoo 심볼 접미사 1:1 매핑.

    KRX_KOSPI/KRX_KOSDAQ 은 한국, NASDAQ/NYSE 는 미국.
    USD 환산 분기 등은 country_code 프로퍼티로 도출.
    """

    KRX_KOSPI = "KRX_KOSPI"
    KRX_KOSDAQ = "KRX_KOSDAQ"
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"

    @property
    def yahoo_suffix(self) -> str:
        """Yahoo ticker 접미사. 미국은 빈 문자열."""
        return {
            Market.KRX_KOSPI: ".KS",
            Market.KRX_KOSDAQ: ".KQ",
            Market.NASDAQ: "",
            Market.NYSE: "",
        }[self]

    @property
    def country_code(self) -> str:
        """그룹핑/표시용 — KR or US 도출."""
        return "KR" if self in (Market.KRX_KOSPI, Market.KRX_KOSDAQ) else "US"
