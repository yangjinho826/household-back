"""account_snapshots 에 월 수입/지출/고정지출 캐시 컬럼 추가

Revision ID: c5f3a1b8e2d4
Revises: 26f899238442
Create Date: 2026-05-15 13:00:00.000000

매월 박제 시 그 달 INCOME/EXPENSE/FIXED_EXPENSE 합계를 같이 박아
조회 시 transactions 재합산 비용 제거. 기존 row 는 transactions 합산으로 백필.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5f3a1b8e2d4"
down_revision: Union[str, Sequence[str], None] = "26f899238442"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_snapshots",
        sa.Column(
            "monthly_income",
            sa.Numeric(15, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "account_snapshots",
        sa.Column(
            "monthly_expense",
            sa.Numeric(15, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "account_snapshots",
        sa.Column(
            "monthly_fixed_expense",
            sa.Numeric(15, 2),
            nullable=False,
            server_default="0",
        ),
    )

    # 백필 — snapshot_date 의 year/month 와 transactions 매칭.
    # data_stat_cd = '50' 은 DataStatus.ACTIVE. TRANSFER 는 제외.
    op.execute(
        """
        UPDATE account_snapshots s SET
          monthly_income = COALESCE((
            SELECT SUM(t.amount) FROM transactions t
            WHERE t.account_id = s.account_id
              AND t.tx_type = 'INCOME'
              AND t.data_stat_cd = '50'
              AND EXTRACT(YEAR FROM t.tx_date) = EXTRACT(YEAR FROM s.snapshot_date)
              AND EXTRACT(MONTH FROM t.tx_date) = EXTRACT(MONTH FROM s.snapshot_date)
          ), 0),
          monthly_expense = COALESCE((
            SELECT SUM(t.amount) FROM transactions t
            WHERE t.account_id = s.account_id
              AND t.tx_type = 'EXPENSE'
              AND t.data_stat_cd = '50'
              AND EXTRACT(YEAR FROM t.tx_date) = EXTRACT(YEAR FROM s.snapshot_date)
              AND EXTRACT(MONTH FROM t.tx_date) = EXTRACT(MONTH FROM s.snapshot_date)
          ), 0),
          monthly_fixed_expense = COALESCE((
            SELECT SUM(t.amount) FROM transactions t
            WHERE t.account_id = s.account_id
              AND t.tx_type = 'FIXED_EXPENSE'
              AND t.data_stat_cd = '50'
              AND EXTRACT(YEAR FROM t.tx_date) = EXTRACT(YEAR FROM s.snapshot_date)
              AND EXTRACT(MONTH FROM t.tx_date) = EXTRACT(MONTH FROM s.snapshot_date)
          ), 0)
        """
    )


def downgrade() -> None:
    op.drop_column("account_snapshots", "monthly_fixed_expense")
    op.drop_column("account_snapshots", "monthly_expense")
    op.drop_column("account_snapshots", "monthly_income")
