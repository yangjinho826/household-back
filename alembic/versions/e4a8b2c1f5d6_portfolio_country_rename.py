"""portfolio_items / portfolio_transactions: ticker→name, symbol→code, country 추가

Revision ID: e4a8b2c1f5d6
Revises: d7e2f8a1b3c4
Create Date: 2026-05-17 14:00:00.000000

야후 파이낸스 연동을 위해 종목 필드 정리:
- ticker (VARCHAR 100)  → name  (종목명, NOT NULL 유지)
- symbol (VARCHAR 50, NULL) → code (종목코드, NOT NULL — NULL 은 빈 문자열로 메움)
- country (VARCHAR 2, NOT NULL, default 'KR') 신규

기존 데이터는 모두 한국 종목으로 가정해 country='KR' 채움.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4a8b2c1f5d6"
down_revision: Union[str, Sequence[str], None] = "d7e2f8a1b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── portfolio_items ───────────────────────────────────────────────
    op.alter_column("portfolio_items", "ticker", new_column_name="name")
    # symbol NULL → '' 메우고 NOT NULL 로
    op.execute("UPDATE portfolio_items SET symbol = '' WHERE symbol IS NULL")
    op.alter_column(
        "portfolio_items",
        "symbol",
        new_column_name="code",
        existing_type=sa.String(length=50),
        nullable=False,
    )
    op.add_column(
        "portfolio_items",
        sa.Column("country", sa.String(length=2), nullable=False, server_default="KR"),
    )
    op.alter_column("portfolio_items", "country", server_default=None)

    # ── portfolio_transactions ────────────────────────────────────────
    op.alter_column("portfolio_transactions", "ticker", new_column_name="name")
    op.execute("UPDATE portfolio_transactions SET symbol = '' WHERE symbol IS NULL")
    op.alter_column(
        "portfolio_transactions",
        "symbol",
        new_column_name="code",
        existing_type=sa.String(length=50),
        nullable=False,
    )
    op.add_column(
        "portfolio_transactions",
        sa.Column("country", sa.String(length=2), nullable=False, server_default="KR"),
    )
    op.alter_column("portfolio_transactions", "country", server_default=None)


def downgrade() -> None:
    # ── portfolio_transactions ────────────────────────────────────────
    op.drop_column("portfolio_transactions", "country")
    op.alter_column(
        "portfolio_transactions",
        "code",
        new_column_name="symbol",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    op.alter_column("portfolio_transactions", "name", new_column_name="ticker")

    # ── portfolio_items ───────────────────────────────────────────────
    op.drop_column("portfolio_items", "country")
    op.alter_column(
        "portfolio_items",
        "code",
        new_column_name="symbol",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    op.alter_column("portfolio_items", "name", new_column_name="ticker")
