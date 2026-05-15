from enum import StrEnum


class PortfolioTxType(StrEnum):
    """자산 거래 종류"""

    BUY = "BUY"
    SELL = "SELL"


class Market(StrEnum):
    """종목 시장 — Yahoo ticker 접미사 매핑 + 갱신 스케줄 분기 용도"""

    KRX_KOSPI = "KRX_KOSPI"
    KRX_KOSDAQ = "KRX_KOSDAQ"
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
