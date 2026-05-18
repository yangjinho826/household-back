"""align_db_with_main_models

Revision ID: 6a6f36efc754
Revises: 9180adc92f4c
Create Date: 2026-05-18 12:39:41.597769

이전 alembic stamp --purge 로 alembic_version 만 main head 로 강제 동기화한 부작용 정리.
실제 DB DDL 은 local 마이그레이션(75dc7468aa90) 적용 상태에 멈춰있어서 main 모델과 불일치.
이 revision 으로 DB 를 main 모델과 일치시킴 — 단방향 (downgrade 의미 없음).

idempotent 하게 작성 — 이미 정상 마이그레이션 경로로 따라온 환경(서버 등)에서
어긋난 부분만 골라 적용하고, 이미 적용된 변경은 조용히 건너뜀.

변경:
- (a) exchange_rates 테이블 drop (local 잔재 — currency_rates 가 대체)
- (b) households.currency 추가 (default 'KRW' 백필)
- (c) portfolio_items: market drop, ticker→name rename, symbol→code rename + NOT NULL, country 추가
- (d) portfolio_transactions: ticker→name rename, symbol→code rename + NOT NULL, country 추가
- (e) transactions.tx_type VARCHAR(10) → VARCHAR(20)
- (f) portfolio_value_history: TIMESTAMP → DateTime(timezone), 인덱스 이름 정렬
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6a6f36efc754"
down_revision: Union[str, Sequence[str], None] = "9180adc92f4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # (a) exchange_rates 테이블 drop — local 잔재
    op.execute("DROP INDEX IF EXISTS uq_exchange_rates_date_pair")
    op.execute("DROP TABLE IF EXISTS exchange_rates")

    # (b) households.currency 추가 — default 'KRW' 백필 후 default 제거
    op.execute(
        "ALTER TABLE households "
        "ADD COLUMN IF NOT EXISTS currency CHAR(3) NOT NULL DEFAULT 'KRW'"
    )
    op.execute("ALTER TABLE households ALTER COLUMN currency DROP DEFAULT")

    # (c) portfolio_items: market drop + ticker→name + symbol→code(NOT NULL) + country 추가
    op.execute("ALTER TABLE portfolio_items DROP COLUMN IF EXISTS market")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'portfolio_items' AND column_name = 'ticker'
            ) THEN
                ALTER TABLE portfolio_items RENAME COLUMN ticker TO name;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'portfolio_items' AND column_name = 'symbol'
            ) THEN
                UPDATE portfolio_items SET symbol = '' WHERE symbol IS NULL;
                ALTER TABLE portfolio_items RENAME COLUMN symbol TO code;
                ALTER TABLE portfolio_items ALTER COLUMN code SET NOT NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        "ALTER TABLE portfolio_items "
        "ADD COLUMN IF NOT EXISTS country VARCHAR(2) NOT NULL DEFAULT 'KR'"
    )
    op.execute("ALTER TABLE portfolio_items ALTER COLUMN country DROP DEFAULT")

    # (d) portfolio_transactions: 동일 패턴 (market 없음)
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'portfolio_transactions' AND column_name = 'ticker'
            ) THEN
                ALTER TABLE portfolio_transactions RENAME COLUMN ticker TO name;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'portfolio_transactions' AND column_name = 'symbol'
            ) THEN
                UPDATE portfolio_transactions SET symbol = '' WHERE symbol IS NULL;
                ALTER TABLE portfolio_transactions RENAME COLUMN symbol TO code;
                ALTER TABLE portfolio_transactions ALTER COLUMN code SET NOT NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        "ALTER TABLE portfolio_transactions "
        "ADD COLUMN IF NOT EXISTS country VARCHAR(2) NOT NULL DEFAULT 'KR'"
    )
    op.execute("ALTER TABLE portfolio_transactions ALTER COLUMN country DROP DEFAULT")

    # (e) transactions.tx_type 길이 확장 — 이미 VARCHAR(20) 이어도 no-op
    op.execute("ALTER TABLE transactions ALTER COLUMN tx_type TYPE VARCHAR(20)")

    # (f) portfolio_value_history: TIMESTAMP → TIMESTAMPTZ, 인덱스 이름 정렬
    op.execute(
        "ALTER TABLE portfolio_value_history "
        "ALTER COLUMN frst_reg_dt TYPE TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE portfolio_value_history "
        "ALTER COLUMN last_mdfcn_dt TYPE TIMESTAMPTZ"
    )
    op.execute("DROP INDEX IF EXISTS ix_pvh_account_id")
    op.execute("DROP INDEX IF EXISTS ix_pvh_household_id")
    op.execute("DROP INDEX IF EXISTS ix_pvh_portfolio_item_id")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pvh_account "
        "ON portfolio_value_history (account_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pvh_household "
        "ON portfolio_value_history (household_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pvh_item_date "
        "ON portfolio_value_history (portfolio_item_id, snapshot_date DESC)"
    )


def downgrade() -> None:
    raise NotImplementedError("drift 정리는 단방향 — downgrade 의미 없음")
