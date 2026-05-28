from app.core.schema import CamelBaseModel


class SettingsOverviewResponse(CamelBaseModel):
    """설정 페이지 진입 응답 — 각 도메인 count 묶음"""

    account_count: int
    category_count: int
    fixed_count: int
    transaction_count: int
    portfolio_count: int
