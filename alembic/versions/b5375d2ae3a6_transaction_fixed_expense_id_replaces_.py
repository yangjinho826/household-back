"""transaction fixed_expense_id replaces is_fixed

Revision ID: b5375d2ae3a6
Revises: be504a39cec0
Create Date: 2026-05-12 18:44:40.346911

transactions:
- is_fixed (bool) 제거
- fixed_expense_id (FK to fixed_expenses.id, nullable, ondelete SET NULL) 추가

기존에 is_fixed=True 였던 거래는 매핑할 fixed_expense 가 없으므로 단순히 제거.
이번달 누적은 fixed_expense_id 가 채워진 거래부터 집계.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5375d2ae3a6"
down_revision: Union[str, Sequence[str], None] = "be504a39cec0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("fixed_expense_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_fixed_expense_id",
        "transactions",
        "fixed_expenses",
        ["fixed_expense_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_column("transactions", "is_fixed")


def downgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column(
            "is_fixed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # server_default 는 마이그레이션 후 제거 (모델은 server_default 없음)
    op.alter_column("transactions", "is_fixed", server_default=None)
    op.drop_constraint(
        "fk_transactions_fixed_expense_id",
        "transactions",
        type_="foreignkey",
    )
    op.drop_column("transactions", "fixed_expense_id")
