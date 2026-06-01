from enum import StrEnum


class AccountType(StrEnum):
    """통장 종류"""

    LIVING = "LIVING"        # 생활
    SAVINGS = "SAVINGS"      # 적립
    INVESTMENT = "INVESTMENT"  # 투자
    REAL_ESTATE = "REAL_ESTATE"  # 부동산 (수동자산 roll-up 전용)
    PENSION = "PENSION"      # 연금 (수동자산 roll-up 전용)
    OTHER = "OTHER"          # 기타
