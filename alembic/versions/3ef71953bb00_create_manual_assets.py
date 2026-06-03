"""create manual_assets

Revision ID: 3ef71953bb00
Revises: b8e4d1a09c37
Create Date: 2026-06-01 21:06:05.205890

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ef71953bb00'
down_revision: Union[str, Sequence[str], None] = 'b8e4d1a09c37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "manual_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("asset_class", sa.String(length=20), nullable=False),
        sa.Column("current_valuation", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("valued_at", sa.Date(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("frst_reg_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_mdfcn_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_stat_cd", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_manual_asset_household", "manual_assets", ["household_id"],
    )
    op.create_index(
        "idx_manual_asset_account", "manual_assets", ["account_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_manual_asset_account", table_name="manual_assets")
    op.drop_index("idx_manual_asset_household", table_name="manual_assets")
    op.drop_table("manual_assets")
