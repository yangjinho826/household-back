from enum import StrEnum


class AccountType(StrEnum):
    """통장 종류"""

    LIVING = "LIVING"        # 생활
    SAVINGS = "SAVINGS"      # 적립
    INVESTMENT = "INVESTMENT"  # 투자
    REAL_ESTATE = "REAL_ESTATE"  # 부동산 (수동자산 roll-up 전용)
    PENSION = "PENSION"      # 연금 (수동자산 roll-up 전용)
    COMMODITY = "COMMODITY"  # 금·원자재 (수동자산 roll-up 전용)
    SAVINGS_ASSET = "SAVINGS_ASSET"  # 적금 (수동자산 — 거래통장 SAVINGS 와 구분)
    OTHER = "OTHER"          # 기타


# 수동자산 전용 통장 타입 — 잔액 = 평가액 + 이체순액. 지출/수입 거래 불가(이체만 허용).
# 배분/스냅샷은 이 타입으로 group by 된다. 곳곳의 하드코딩 튜플을 이 상수로 통일.
MANUAL_ASSET_ACCOUNT_TYPES = (
    AccountType.REAL_ESTATE,
    AccountType.PENSION,
    AccountType.COMMODITY,
    AccountType.SAVINGS_ASSET,
)
