"""portfolio_value_history 에 asset_class(박제 시점 자산 성격) 컬럼 추가

Revision ID: c9d4e7f21a36
Revises: 3ef71953bb00
Create Date: 2026-06-01 22:00:00.000000

월별 자산군 배분추이(R5a-3) 재구성용. 종목 박제 시 그 시점 asset_class 를 같이 박아,
나중에 종목을 재분류해도 과거 달 배분추이가 거짓이 되지 않게 한다.
기존 박제행은 현재 portfolio_items.asset_class 로 백필(과거 시점 분류 이력은 없으므로 현재값).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d4e7f21a36"
down_revision: Union[str, Sequence[str], None] = "3ef71953bb00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "portfolio_value_history",
        sa.Column(
            "asset_class",
            sa.String(20),
            nullable=False,
            server_default="STOCK",
        ),
    )
    # 기존 박제행 백필 — 종목의 현재 분류로 채움
    op.execute(
        """
        UPDATE portfolio_value_history AS pvh
        SET asset_class = pi.asset_class
        FROM portfolio_items AS pi
        WHERE pvh.portfolio_item_id = pi.id
        """
    )


def downgrade() -> None:
    op.drop_column("portfolio_value_history", "asset_class")
