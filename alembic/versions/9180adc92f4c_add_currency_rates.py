"""add_currency_rates

Revision ID: 9180adc92f4c
Revises: e4a8b2c1f5d6
Create Date: 2026-05-18 09:32:45.620563

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9180adc92f4c"
down_revision: Union[str, Sequence[str], None] = "e4a8b2c1f5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "currency_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("base_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("quote_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("frst_reg_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_mdfcn_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_stat_cd", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "base_currency", "quote_currency",
            name="uq_currency_rates_pair",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("currency_rates")
