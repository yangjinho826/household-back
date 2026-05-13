"""drop fixed_expenses amount

Revision ID: a9668f7687a9
Revises: b5375d2ae3a6
Create Date: 2026-05-13 10:50:07.042957

fixed_expenses 는 더 이상 금액(amount) 을 직접 보관하지 않는다.
실제 금액은 transactions.fixed_expense_id 매핑된 거래에서 가져온다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9668f7687a9"
down_revision: Union[str, Sequence[str], None] = "b5375d2ae3a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("fixed_expenses", "amount")


def downgrade() -> None:
    op.add_column(
        "fixed_expenses",
        sa.Column("amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
    )
    op.alter_column("fixed_expenses", "amount", server_default=None)
