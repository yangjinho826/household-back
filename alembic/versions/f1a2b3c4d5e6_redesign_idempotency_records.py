"""redesign idempotency_records: uuid PK + status + fingerprint

Revision ID: f1a2b3c4d5e6
Revises: 7033d7e28bc7
Create Date: 2026-05-22

복합 PK → uuid 단일 PK + UNIQUE(user_id, key).
status / request_fingerprint / response_headers / completed_at 컬럼 추가.
운영 데이터 없으므로 drop + recreate.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "7033d7e28bc7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_idempotency_records_created_at", table_name="idempotency_records")
    op.drop_table("idempotency_records")

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_headers", sa.Text(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
    )
    op.create_index(
        "ix_idempotency_status_created",
        "idempotency_records",
        ["status", "created_at"],
    )


def downgrade() -> None:
    # 이전 1차 스키마로 복원하지 않음 — 단방향
    op.drop_index("ix_idempotency_status_created", table_name="idempotency_records")
    op.drop_table("idempotency_records")
