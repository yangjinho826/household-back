"""add categories kind check

Revision ID: 26f899238442
Revises: a9668f7687a9
Create Date: 2026-05-13 21:02:09.778929

categories.kind 는 EXPENSE / INCOME 만 허용.
과거에 TRANSFER 등 비정상 값이 들어가 CategoryKind 변환 시 ValueError 발생한 사례 방지.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "26f899238442"
down_revision: Union[str, Sequence[str], None] = "a9668f7687a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK 추가 전 비정상 데이터 정리 (idempotent — 이미 정리됐어도 무해)
    op.execute("DELETE FROM categories WHERE kind NOT IN ('EXPENSE', 'INCOME')")
    op.create_check_constraint(
        "ck_categories_kind",
        "categories",
        "kind IN ('EXPENSE', 'INCOME')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_categories_kind", "categories", type_="check")
