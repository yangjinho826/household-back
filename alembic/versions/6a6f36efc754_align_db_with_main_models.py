"""align_db_with_main_models

Revision ID: 6a6f36efc754
Revises: 9180adc92f4c
Create Date: 2026-05-18 12:39:41.597769

이전 alembic stamp --purge 로 alembic_version 만 main head 로 강제 동기화한 부작용 정리.
실제 DB DDL 은 local 마이그레이션(75dc7468aa90) 적용 상태에 멈춰있어서 main 모델과 불일치.
이 revision 으로 DB 를 main 모델과 일치시킴 — 단방향 (downgrade 의미 없음).

변경:
- (a) exchange_rates 테이블 drop (local 잔재 — currency_rates 가 대체)
- (b) households.currency 추가 (default 'KRW' 백필)
- (c) portfolio_items: market drop, ticker→name rename, symbol→code rename + NOT NULL, country 추가
- (d) portfolio_transactions: ticker→name rename, symbol→code rename + NOT NULL, country 추가
- (e) transactions.tx_type VARCHAR(10) → VARCHAR(20)
- (f) portfolio_value_history: TIMESTAMP → DateTime(timezone), 인덱스 이름 정렬
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6a6f36efc754"
down_revision: Union[str, Sequence[str], None] = "9180adc92f4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # (a) exchange_rates 테이블 drop — local 잔재
    op.drop_index("uq_exchange_rates_date_pair", table_name="exchange_rates")
    op.drop_table("exchange_rates")

    # (b) households.currency 추가 — default 'KRW' 백필 → 새 row 명시 강제
    op.add_column(
        "households",
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default="KRW"),
    )
    op.alter_column("households", "currency", server_default=None)

    # (c) portfolio_items: market drop + main 의 e4a8b2c1f5d6 재현
    op.drop_column("portfolio_items", "market")
    op.alter_column("portfolio_items", "ticker", new_column_name="name")
    op.execute("UPDATE portfolio_items SET symbol = '' WHERE symbol IS NULL")
    op.alter_column(
        "portfolio_items",
        "symbol",
        new_column_name="code",
        existing_type=sa.String(50),
        nullable=False,
    )
    op.add_column(
        "portfolio_items",
        sa.Column("country", sa.String(2), nullable=False, server_default="KR"),
    )
    op.alter_column("portfolio_items", "country", server_default=None)

    # (d) portfolio_transactions: 동일 패턴 (market 없음)
    op.alter_column("portfolio_transactions", "ticker", new_column_name="name")
    op.execute("UPDATE portfolio_transactions SET symbol = '' WHERE symbol IS NULL")
    op.alter_column(
        "portfolio_transactions",
        "symbol",
        new_column_name="code",
        existing_type=sa.String(50),
        nullable=False,
    )
    op.add_column(
        "portfolio_transactions",
        sa.Column("country", sa.String(2), nullable=False, server_default="KR"),
    )
    op.alter_column("portfolio_transactions", "country", server_default=None)

    # (e) transactions.tx_type 길이 확장
    op.alter_column(
        "transactions",
        "tx_type",
        existing_type=sa.VARCHAR(10),
        type_=sa.String(20),
        existing_nullable=False,
    )

    # (f) portfolio_value_history 타입/인덱스 정렬
    op.alter_column(
        "portfolio_value_history",
        "frst_reg_dt",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "portfolio_value_history",
        "last_mdfcn_dt",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index("ix_pvh_account_id", table_name="portfolio_value_history")
    op.drop_index("ix_pvh_household_id", table_name="portfolio_value_history")
    op.drop_index("ix_pvh_portfolio_item_id", table_name="portfolio_value_history")
    op.create_index(
        "idx_pvh_account", "portfolio_value_history", ["account_id"], unique=False,
    )
    op.create_index(
        "idx_pvh_household", "portfolio_value_history", ["household_id"], unique=False,
    )
    op.create_index(
        "idx_pvh_item_date",
        "portfolio_value_history",
        ["portfolio_item_id", sa.literal_column("snapshot_date DESC")],
        unique=False,
    )


def downgrade() -> None:
    raise NotImplementedError("drift 정리는 단방향 — downgrade 의미 없음")
