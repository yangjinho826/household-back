"""과거 매도(realized_pnl NULL) 실현손익 백필

realized_pnl 컬럼(a3f7c9d2e1b8)이 생기기 전에 일어난 SELL 은 손익이 NULL 이라
화면에서 "실현손익 0원 / 매수금액 0원" 으로 보인다(매도금액은 거래에서 직접 계산).

종목별 거래를 시간순(tx_date ASC, frst_reg_dt ASC)으로 replay 하며 매도시점
이동평균 평단으로 realized_pnl / realized_cost_basis 를 재박제한다.
service._recompute_realized_pnl 과 동일한 알고리즘.

대상: realized_pnl IS NULL 인 SELL 을 하나라도 가진 종목(portfolio_item_id).
이미 다 박제된 종목은 건드리지 않는다. portfolio_item_id 가 NULL 인 SELL 은
종목으로 묶을 수 없어(매도시점 평단 복원 불가) skip 한다.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5e7f9a1b2"
down_revision: Union[str, Sequence[str], None] = "b2d3f4a5c6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CENT = Decimal("0.01")


def upgrade() -> None:
    conn = op.get_bind()

    # NULL SELL 을 가진 종목만 대상 — 이미 박제된 종목은 제외
    item_ids = conn.execute(
        sa.text(
            """
            SELECT DISTINCT portfolio_item_id
            FROM portfolio_transactions
            WHERE pt_type = 'SELL'
              AND realized_pnl IS NULL
              AND portfolio_item_id IS NOT NULL
              AND data_stat_cd = '50'
            """
        )
    ).scalars().all()

    for item_id in item_ids:
        rows = conn.execute(
            sa.text(
                """
                SELECT id, pt_type, quantity, price
                FROM portfolio_transactions
                WHERE portfolio_item_id = :iid
                  AND data_stat_cd = '50'
                ORDER BY tx_date ASC, frst_reg_dt ASC
                """
            ),
            {"iid": item_id},
        ).mappings().all()

        running_qty = Decimal("0")
        running_cost = Decimal("0")
        for r in rows:
            qty = Decimal(str(r["quantity"]))
            price = Decimal(str(r["price"]))
            if r["pt_type"] == "BUY":
                running_qty += qty
                running_cost += qty * price
            elif r["pt_type"] == "SELL":
                running_avg = (
                    running_cost / running_qty if running_qty > 0 else Decimal("0")
                )
                cost_basis = (running_avg * qty).quantize(
                    _CENT, rounding=ROUND_HALF_UP
                )
                pnl = ((price - running_avg) * qty).quantize(
                    _CENT, rounding=ROUND_HALF_UP
                )
                conn.execute(
                    sa.text(
                        """
                        UPDATE portfolio_transactions
                        SET realized_pnl = :pnl, realized_cost_basis = :cost
                        WHERE id = :id
                        """
                    ),
                    {"pnl": pnl, "cost": cost_basis, "id": r["id"]},
                )
                # 매도는 평단 불변 — 평단 비율로 수량/원가 차감
                running_cost -= running_avg * qty
                running_qty -= qty


def downgrade() -> None:
    # 데이터 백필 — 원래 어떤 SELL 이 NULL 이었는지 복원 불가하므로 no-op.
    pass
