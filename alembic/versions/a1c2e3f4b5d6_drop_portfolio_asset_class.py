"""portfolio_items 에서 asset_class 컬럼 제거

Revision ID: a1c2e3f4b5d6
Revises: c9d4e7f21a36
Create Date: 2026-06-02 09:00:00.000000

종목 단위 자산 성격 분류 폐지(R5b-①). 종목은 자산군 배분에서 전부 INVESTMENT 한
덩어리로 집계되므로 종목별 asset_class 가 불필요해짐. b8e4d1a09c37 의 역연산.
downgrade 는 컬럼을 server_default 'STOCK' 으로 복원(원래도 그게 기본값이라 무손실).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c2e3f4b5d6"
down_revision: Union[str, Sequence[str], None] = "c9d4e7f21a36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("portfolio_items", "asset_class")


def downgrade() -> None:
    op.add_column(
        "portfolio_items",
        sa.Column(
            "asset_class",
            sa.String(20),
            nullable=False,
            server_default="STOCK",
        ),
    )
