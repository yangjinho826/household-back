from enum import StrEnum


class AccountType(StrEnum):
    """통장 종류"""

    LIVING = "LIVING"        # 생활
    SAVINGS = "SAVINGS"      # 적립
    INVESTMENT = "INVESTMENT"  # 투자
