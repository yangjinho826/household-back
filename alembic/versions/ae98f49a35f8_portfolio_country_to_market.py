"""portfolio_country_to_market

Revision ID: ae98f49a35f8
Revises: 6a6f36efc754
Create Date: 2026-05-18 15:50:29.897468

portfolio_items / portfolio_transactions:
  - country (String 2) drop
  - market (String 20) add — Market enum (KRX_KOSPI/KRX_KOSDAQ/NASDAQ/NYSE)

기존 row 는 일괄 'KRX_KOSPI' 백필 (로컬 2개 모두 한국 종목). 코스닥/미국 종목 있으면 추후 SQL UPDATE 수동 정정.

downgrade 는 단방향 — country→market 의미 매핑이 단순 default 라 역변환 의미 없음.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ae98f49a35f8"
down_revision: Union[str, Sequence[str], None] = "6a6f36efc754"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # portfolio_items
    op.add_column(
        "portfolio_items",
        sa.Column("market", sa.String(20), nullable=False, server_default="KRX_KOSPI"),
    )
    op.alter_column("portfolio_items", "market", server_default=None)
    op.drop_column("portfolio_items", "country")

    # portfolio_transactions
    op.add_column(
        "portfolio_transactions",
        sa.Column("market", sa.String(20), nullable=False, server_default="KRX_KOSPI"),
    )
    op.alter_column("portfolio_transactions", "market", server_default=None)
    op.drop_column("portfolio_transactions", "country")


def downgrade() -> None:
    raise NotImplementedError("country→market 단방향 — downgrade 의미 없음")
