"""portfolio_value_history 에서 asset_class 컬럼 제거

Revision ID: b2d3f4a5c6e7
Revises: a1c2e3f4b5d6
Create Date: 2026-06-02 09:01:00.000000

종목 분류 폐지(R5b-①)에 따라 박제 시점 asset_class 도 불필요. 배분추이에서 종목은
전부 INVESTMENT 로 합산되므로 박제 분류값을 더 이상 읽지 않는다. c9d4e7f21a36 역연산.
downgrade 는 컬럼을 server_default 'STOCK' 으로 복원하나, 과거 분류 이력은 복원 불가
(c9d4e7f21a36 도 현재값 백필이었던 것과 동일한 한계 — 컬럼 구조만 복원).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2d3f4a5c6e7"
down_revision: Union[str, Sequence[str], None] = "a1c2e3f4b5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("portfolio_value_history", "asset_class")


def downgrade() -> None:
    op.add_column(
        "portfolio_value_history",
        sa.Column(
            "asset_class",
            sa.String(20),
            nullable=False,
            server_default="STOCK",
        ),
    )
