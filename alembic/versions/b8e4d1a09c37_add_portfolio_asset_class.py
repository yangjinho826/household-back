"""portfolio_items 에 asset_class(자산 성격) 컬럼 추가

Revision ID: b8e4d1a09c37
Revises: a3f7c9d2e1b8
Create Date: 2026-06-01 16:00:00.000000

market(거래소)와 직교하는 자산 성격 축. 금을 KRX_KOSPI 에 욱여넣던 문제 해소.
기존 종목은 전부 STOCK 기본값 — 금 등은 사용자가 UI 에서 직접 재분류(SQL 추측 안 함).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8e4d1a09c37"
down_revision: Union[str, Sequence[str], None] = "a3f7c9d2e1b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "portfolio_items",
        sa.Column(
            "asset_class",
            sa.String(20),
            nullable=False,
            server_default="STOCK",
        ),
    )


def downgrade() -> None:
    op.drop_column("portfolio_items", "asset_class")
