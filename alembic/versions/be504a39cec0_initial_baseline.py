"""initial baseline

Revision ID: be504a39cec0
Revises:
Create Date: 2026-05-12 18:43:23.827017

이미 운영 중인 DB 와 모델 사이의 미세한 차이 (DateTime vs TIMESTAMP, 인덱스명 등)
는 autogenerate 가 잡았지만 운영 데이터 보호를 위해 baseline 은 빈 마이그레이션으로
둔다. 운영 DB 는 `alembic stamp head` 로 head 적용 상태로 표시하고, 이후 변경은
새 revision 으로만 관리한다.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "be504a39cec0"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
