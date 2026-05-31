"""portfolio_transactions 에 매도 실현손익 컬럼 추가

Revision ID: a3f7c9d2e1b8
Revises: f1a2b3c4d5e6
Create Date: 2026-05-31 23:00:00.000000

매도(SELL) 거래마다 매도시점 이동평균 평단 기준 실현손익을 건별 박제한다.
- realized_pnl: (매도단가 - 매도시점 평단) * 수량
- realized_cost_basis: 매도시점 평단 * 수량 (검증/매수금액 표시용)
둘 다 nullable — BUY 거래와 R2 이전 SELL 은 NULL (매도시점 평단 복원 불가).
백필 없음.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f7c9d2e1b8"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "portfolio_transactions",
        sa.Column("realized_pnl", sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        "portfolio_transactions",
        sa.Column("realized_cost_basis", sa.Numeric(15, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_transactions", "realized_cost_basis")
    op.drop_column("portfolio_transactions", "realized_pnl")
