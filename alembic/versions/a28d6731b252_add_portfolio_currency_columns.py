"""add portfolio currency columns

Revision ID: a28d6731b252
Revises: 4851000e13bd
Create Date: 2026-08-17 15:33:11.728275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a28d6731b252'
down_revision: Union[str, Sequence[str], None] = '4851000e13bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """거래통화 병행 보관 컬럼.

    KRW 컬럼은 그대로 진실 원천으로 남는다 — 계좌잔액·순자산·스냅샷 합산이
    통화 구분 없이 더하기 때문에 전환하면 달러와 원이 섞인다.

    `*_ccy` 는 전부 nullable 이고 기존 row 는 NULL 로 둔다. 기존 NASDAQ/NYSE 거래의
    price 는 이미 원화 환산값이고 원본 달러가와 당시 환율은 저장된 적이 없다.
    price 를 그대로 넣으면 달러 칸에 원화가 들어가고, 현재 환율로 나누면 과거
    거래에 오늘 환율을 씌운 가짜 매수가가 된다. NULL = '모른다'.
    """
    op.add_column(
        "portfolio_items",
        sa.Column("currency", sa.String(3), nullable=False, server_default="KRW"),
    )
    op.add_column(
        "portfolio_items", sa.Column("avg_price_ccy", sa.Numeric(15, 4), nullable=True),
    )
    op.add_column(
        "portfolio_items",
        sa.Column("current_price_ccy", sa.Numeric(15, 4), nullable=True),
    )

    op.add_column(
        "portfolio_transactions",
        sa.Column("currency", sa.String(3), nullable=False, server_default="KRW"),
    )
    op.add_column(
        "portfolio_transactions",
        sa.Column("price_ccy", sa.Numeric(15, 4), nullable=True),
    )
    op.add_column(
        "portfolio_transactions",
        sa.Column("fee_ccy", sa.Numeric(15, 4), nullable=True),
    )
    op.add_column(
        "portfolio_transactions",
        sa.Column("fx_rate", sa.Numeric(15, 4), nullable=False, server_default="1"),
    )
    op.add_column(
        "portfolio_transactions",
        sa.Column("realized_pnl_ccy", sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        "portfolio_transactions",
        sa.Column("realized_cost_basis_ccy", sa.Numeric(15, 2), nullable=True),
    )

    # 국내 종목은 원화가 곧 거래통화라 원본을 그대로 복사해도 참이다.
    # 해외(NASDAQ/NYSE)는 손대지 않는다 — 위 docstring 참조.
    op.execute(
        """
        UPDATE portfolio_transactions
           SET price_ccy = price, fee_ccy = fee
         WHERE market NOT IN ('NASDAQ', 'NYSE')
        """
    )
    op.execute(
        """
        UPDATE portfolio_items
           SET avg_price_ccy = avg_price, current_price_ccy = current_price
         WHERE market NOT IN ('NASDAQ', 'NYSE')
        """
    )
    op.execute(
        """
        UPDATE portfolio_items SET currency = 'USD'
         WHERE market IN ('NASDAQ', 'NYSE')
        """
    )
    op.execute(
        """
        UPDATE portfolio_transactions SET currency = 'USD'
         WHERE market IN ('NASDAQ', 'NYSE')
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    for col in ("realized_cost_basis_ccy", "realized_pnl_ccy", "fx_rate",
                "fee_ccy", "price_ccy", "currency"):
        op.drop_column("portfolio_transactions", col)
    for col in ("current_price_ccy", "avg_price_ccy", "currency"):
        op.drop_column("portfolio_items", col)
