from enum import StrEnum


class TxType(StrEnum):
    """거래 종류"""

    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    TRANSFER = "TRANSFER"
    # 고정 지출 — `fixed_expense_id` 가 필수. 통계에선 EXPENSE 와 함께 지출로 집계.
    FIXED_EXPENSE = "FIXED_EXPENSE"
