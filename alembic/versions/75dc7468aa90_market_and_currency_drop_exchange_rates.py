"""market_and_currency_drop_exchange_rates

Revision ID: 75dc7468aa90
Revises: c5f3a1b8e2d4
Create Date: 2026-05-15 14:57:22.161595

세 가지를 한 revision 에 묶음:
1. exchange_rates 테이블 신설 — USD/KRW 시계열 환율 박제
2. portfolio_items.market 컬럼 추가 — Yahoo ticker 매핑 + 갱신 스케줄 분기
   (기존 row 는 KRX_KOSPI 로 backfill 후 server_default 제거 → 새 row 명시 강제)
3. households.currency 컬럼 제거 — 가계부 전체 KRW 단일화
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "75dc7468aa90"
down_revision: Union[str, Sequence[str], None] = "c5f3a1b8e2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. exchange_rates 테이블 신설
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("quote_currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(15, 4), nullable=False),
        sa.Column("data_stat_cd", sa.String(30), nullable=False),
        sa.Column("frst_reg_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_mdfcn_dt", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_exchange_rates_date_pair",
        "exchange_rates",
        ["snapshot_date", "base_currency", "quote_currency"],
        unique=True,
    )

    # 2. portfolio_items.market 컬럼 추가 (기존 row 는 KRX_KOSPI 로 backfill)
    op.add_column(
        "portfolio_items",
        sa.Column(
            "market",
            sa.String(20),
            nullable=False,
            server_default="KRX_KOSPI",
        ),
    )
    # 새 row 는 명시 강제 — server_default 제거
    op.alter_column("portfolio_items", "market", server_default=None)

    # 3. households.currency 제거 — 가계부 전체 KRW 단일화
    op.drop_column("households", "currency")


def downgrade() -> None:
    # 1. households.currency 복원 (모든 row 기본값 'KRW')
    op.add_column(
        "households",
        sa.Column(
            "currency",
            sa.CHAR(3),
            nullable=False,
            server_default="KRW",
        ),
    )
    op.alter_column("households", "currency", server_default=None)

    # 2. portfolio_items.market 제거
    op.drop_column("portfolio_items", "market")

    # 3. exchange_rates 테이블 제거
    op.drop_index("uq_exchange_rates_date_pair", table_name="exchange_rates")
    op.drop_table("exchange_rates")
