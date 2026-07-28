"""add market_price_history

Revision ID: a7c3e9d1f4b8
Revises: c8e1f4a7d2b9
Create Date: 2026-07-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9d1f4b8"
down_revision: Union[str, Sequence[str], None] = "c8e1f4a7d2b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_price_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("frst_reg_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_mdfcn_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_stat_cd", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "code", "market", "price_date", name="uq_market_price_code_market_date",
        ),
    )
    op.create_index(
        "ix_market_price_lookup",
        "market_price_history",
        ["code", "market", "price_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_price_lookup", table_name="market_price_history")
    op.drop_table("market_price_history")
