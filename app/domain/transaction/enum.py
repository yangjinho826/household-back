from enum import StrEnum


class TxType(StrEnum):
    """거래 종류"""

    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    TRANSFER = "TRANSFER"
    # 고정 지출 — `fixed_expense_id` 가 필수. 통계에선 EXPENSE 와 함께 지출로 집계.
    FIXED_EXPENSE = "FIXED_EXPENSE"
    # 평가조정 — 수동자산 가치 변동(시세·이자 등 현금 유입 없는 증감). 상대계좌 없는 단독 거래.
    # amount 는 양수, 증감은 valuation_direction 으로 표현. 모든 통계 집계에서 제외(잔액에만 반영).
    VALUATION = "VALUATION"


class ValuationDirection(StrEnum):
    """평가조정(VALUATION) 거래의 증감 방향 — 그 외 타입에는 존재하지 않는다."""

    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
