from decimal import Decimal

from app.core.schema import CamelBaseModel
from app.core.types import Money
from app.domain.account.schema import AccountResponse
from app.domain.stats.schema import MonthlyStatsResponse
from app.domain.transaction.schema import TransactionResponse


class HomeOverviewResponse(CamelBaseModel):
    """홈 페이지 진입 응답 — 총 잔액 + 통장 목록 + 최근 거래 + 월간 stats 한 번에"""

    total_balance: Money
    accounts: list[AccountResponse]
    recent_transactions: list[TransactionResponse]
    stats: MonthlyStatsResponse
    year: int
    month: int


def zero_total_balance() -> Decimal:
    return Decimal("0")
