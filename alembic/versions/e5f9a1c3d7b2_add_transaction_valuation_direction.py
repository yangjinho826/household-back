"""transactions.valuation_direction 추가 (평가조정 거래)

Revision ID: e5f9a1c3d7b2
Revises: d4e6f8a0b2c4
Create Date: 2026-06-04 00:00:00.000000

평가조정(VALUATION) 거래의 증감 방향(INCREASE/DECREASE) 저장 컬럼. 그 외 타입은 NULL.
tx_type 은 이미 VARCHAR(20) + CHECK 제약 없음이라 VALUATION 문자열 수용에 별도 변경 불필요.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f9a1c3d7b2"
down_revision: Union[str, Sequence[str], None] = "d4e6f8a0b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("valuation_direction", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "valuation_direction")
