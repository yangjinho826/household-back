"""add portfolio_transactions fee

Revision ID: 4851000e13bd
Revises: a7c3e9d1f4b8
Create Date: 2026-08-17 14:46:09.505246

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4851000e13bd'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9d1f4b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """매매 수수료 컬럼 추가.

    server_default='0' 이라 기존 row 는 전부 0 으로 채워지고, replay 계산이
    도입 전과 같은 값을 낸다(회귀 없음). NOT NULL 로 두어 '수수료 미입력'과
    '수수료 0원'을 구분하지 않는다 — 미입력은 0원과 같은 의미다.
    """
    op.add_column(
        "portfolio_transactions",
        sa.Column(
            "fee",
            sa.Numeric(15, 2),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("portfolio_transactions", "fee")
