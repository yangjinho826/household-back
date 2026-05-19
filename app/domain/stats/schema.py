from uuid import UUID

from app.core.schema import CamelBaseModel
from app.core.types import Money, Rate


class CategoryStatsItem(CamelBaseModel):
    """카테고리별 합계 1건"""

    category_id: UUID
    name: str
    icon: str | None
    color: str | None
    is_income: bool
    amount: Money
    ratio: Rate  # 0.00 ~ 1.00 — 같은 kind 내 max 대비


class MonthlyStatsResponse(CamelBaseModel):
    year: int
    month: int
    monthly_income: Money
    monthly_expense: Money
    monthly_transfer: Money
    by_category: list[CategoryStatsItem]
