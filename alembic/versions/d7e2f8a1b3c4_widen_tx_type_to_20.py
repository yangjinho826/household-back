"""transactions.tx_type VARCHAR(10) → VARCHAR(20)

Revision ID: d7e2f8a1b3c4
Revises: c5f3a1b8e2d4
Create Date: 2026-05-15 23:50:00.000000

TxType.FIXED_EXPENSE (13자) 추가 후 기존 VARCHAR(10) 컬럼에 들어가지 못해
StringDataRightTruncationError 발생. 향후 확장 여지 포함해 20자로 확장.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7e2f8a1b3c4"
down_revision: Union[str, Sequence[str], None] = "c5f3a1b8e2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "transactions",
        "tx_type",
        existing_type=sa.String(length=10),
        type_=sa.String(length=20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "transactions",
        "tx_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
