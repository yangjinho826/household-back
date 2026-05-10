from enum import StrEnum


class PortfolioTxType(StrEnum):
    """자산 거래 종류"""

    BUY = "BUY"
    SELL = "SELL"
