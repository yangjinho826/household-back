from enum import StrEnum


class TxType(StrEnum):
    """거래 종류"""

    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    TRANSFER = "TRANSFER"
