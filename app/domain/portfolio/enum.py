from enum import StrEnum


class PortfolioTxType(StrEnum):
    """자산 거래 종류"""

    BUY = "BUY"
    SELL = "SELL"


class Country(StrEnum):
    """종목 소속 국가 — 야후 파이낸스 심볼 조합 기준"""

    KR = "KR"
    US = "US"
