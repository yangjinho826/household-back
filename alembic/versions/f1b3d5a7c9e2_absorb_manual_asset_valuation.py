"""수동자산 평가액을 전용계좌 start_balance 로 흡수

Revision ID: f1b3d5a7c9e2
Revises: e5f9a1c3d7b2
Create Date: 2026-06-04 00:00:01.000000

ManualAsset.current_valuation 을 1:1 전용계좌의 start_balance 로 합산. 잔액 공식이
'평가액 + 이체' → 'start_balance + 이체(+평가조정)' 으로 바뀌어도 기존 balance 가 무손실.
(흡수 전 수동자산 통장 start_balance 는 0 — split 마이그레이션이 0 으로 생성.)

manual_assets 테이블/도메인 제거는 후속 단계에서 별도로. 롤백 안전을 위해 흡수만 수행.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1b3d5a7c9e2"
down_revision: Union[str, Sequence[str], None] = "e5f9a1c3d7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # 활성 수동자산(data_stat_cd='50')의 평가액 합을 대응 전용계좌 start_balance 에 가산.
    conn.execute(
        sa.text(
            """
            UPDATE accounts AS a
            SET start_balance = a.start_balance + sub.total
            FROM (
                SELECT account_id, SUM(current_valuation) AS total
                FROM manual_assets
                WHERE data_stat_cd = '50'
                GROUP BY account_id
            ) AS sub
            WHERE sub.account_id = a.id
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE accounts AS a
            SET start_balance = a.start_balance - sub.total
            FROM (
                SELECT account_id, SUM(current_valuation) AS total
                FROM manual_assets
                WHERE data_stat_cd = '50'
                GROUP BY account_id
            ) AS sub
            WHERE sub.account_id = a.id
            """
        )
    )
