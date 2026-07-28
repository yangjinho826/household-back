"""과거 account_snapshots.balance + portfolio_value_history 를 as-of 원가로 백필

기존 박제는 balance 를 박제 당시의 현재 누적 잔액으로 저장하고, PVH 는 과거 월에도
'현재 보유종목'을 저장했다. 그래서 as-of 현금과 현재 보유가 섞여 이중계상됐다
(예: 6월에 산 주식을, 그 매수대금이 아직 현금이던 5월 잔액에도 포함).

이 마이그레이션은 각 투자계좌 스냅샷을 '그 달 말일 시점 보유'로 재구성한다:
- cash_asof = start_balance + income - expense - transfer_out + transfer_in
             + valuation_net - buy_notional + sell_notional  (모두 tx_date <= 말일)
- 보유수량 = Σbuy_qty - Σsell_qty (종목별, <= 말일), 순수량 0 이하는 제외
- valuation = Σ(보유수량 × 매수평단)  ← 과거 시가 이력이 없어 원가 기준
- balance = cash_asof + valuation

그 달 PVH 행을 as-of 보유(원가)로 replace(DELETE+INSERT) 하므로
wealth 의 `balance - Σpvh_valuation = cash_asof (>= 0)` 역산이 정합·안전하다.
현금/수동자산 계좌는 cash 만 as-of 로 재계산(PVH 없음).

실행 전 백업 권장 (둘 다):
  pg_dump -t account_snapshots -t portfolio_value_history <db> > backup.sql
변경 행은 stdout 에 old -> new diff 로 남는다. downgrade 는 복원 불가라 no-op.
"""
import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8e1f4a7d2b9"
down_revision: Union[str, Sequence[str], None] = "f1b3d5a7c9e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CENT = Decimal("0.01")
_ACTIVE = "50"
_INVESTMENT = "INVESTMENT"


def _d(v) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal("0")


def _month_end(d: date) -> date:
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


def _cash_asof(conn, acc, as_of, *, investment: bool) -> Decimal:
    """account.service._cash_flow 와 동일 공식의 as-of 현금."""
    row = conn.execute(
        sa.text(
            """
            SELECT
              COALESCE(SUM(CASE WHEN tx_type='INCOME' AND account_id=:acc THEN amount ELSE 0 END),0) AS income,
              COALESCE(SUM(CASE WHEN tx_type IN ('EXPENSE','FIXED_EXPENSE') AND account_id=:acc THEN amount ELSE 0 END),0) AS expense,
              COALESCE(SUM(CASE WHEN tx_type='TRANSFER' AND account_id=:acc THEN amount ELSE 0 END),0) AS transfer_out,
              COALESCE(SUM(CASE WHEN tx_type='TRANSFER' AND to_account_id=:acc THEN amount ELSE 0 END),0) AS transfer_in,
              COALESCE(SUM(CASE WHEN tx_type='VALUATION' AND account_id=:acc AND valuation_direction='INCREASE' THEN amount ELSE 0 END),0) AS val_inc,
              COALESCE(SUM(CASE WHEN tx_type='VALUATION' AND account_id=:acc AND valuation_direction='DECREASE' THEN amount ELSE 0 END),0) AS val_dec
            FROM transactions
            WHERE data_stat_cd=:active AND tx_date <= :as_of
              AND (account_id=:acc OR to_account_id=:acc)
            """
        ),
        {"acc": acc, "as_of": as_of, "active": _ACTIVE},
    ).mappings().one()

    start = conn.execute(
        sa.text("SELECT start_balance FROM accounts WHERE id=:acc"),
        {"acc": acc},
    ).scalar()

    cash = (
        _d(start)
        + _d(row["income"]) - _d(row["expense"])
        - _d(row["transfer_out"]) + _d(row["transfer_in"])
        + _d(row["val_inc"]) - _d(row["val_dec"])
    )

    if investment:
        pt = conn.execute(
            sa.text(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN pt_type='BUY' THEN quantity*price ELSE 0 END),0) AS buy,
                  COALESCE(SUM(CASE WHEN pt_type='SELL' THEN quantity*price ELSE 0 END),0) AS sell
                FROM portfolio_transactions
                WHERE data_stat_cd=:active AND account_id=:acc AND tx_date <= :as_of
                """
            ),
            {"acc": acc, "as_of": as_of, "active": _ACTIVE},
        ).mappings().one()
        cash = cash - _d(pt["buy"]) + _d(pt["sell"])

    return cash


def _asof_holdings(conn, acc, as_of) -> list[dict]:
    """as_of 시점 보유 종목 재구성 — repository.asof_holdings_by_account 와 동일 로직."""
    rows = conn.execute(
        sa.text(
            """
            SELECT portfolio_item_id AS item_id,
                   MAX(name) AS name, MAX(code) AS code, MAX(market) AS market,
                   SUM(CASE WHEN pt_type='BUY' THEN quantity WHEN pt_type='SELL' THEN -quantity ELSE 0 END) AS qty,
                   SUM(CASE WHEN pt_type='BUY' THEN quantity ELSE 0 END) AS buy_qty,
                   SUM(CASE WHEN pt_type='BUY' THEN quantity*price ELSE 0 END) AS buy_amt
            FROM portfolio_transactions
            WHERE data_stat_cd=:active AND account_id=:acc AND tx_date <= :as_of
              AND portfolio_item_id IS NOT NULL
            GROUP BY portfolio_item_id
            """
        ),
        {"acc": acc, "as_of": as_of, "active": _ACTIVE},
    ).mappings().all()

    holdings: list[dict] = []
    for r in rows:
        qty = _d(r["qty"])
        if qty <= 0:
            continue
        bq = _d(r["buy_qty"])
        ba = _d(r["buy_amt"])
        avg_cost = (ba / bq) if bq > 0 else Decimal("0")
        holdings.append({
            "item_id": r["item_id"],
            "name": r["name"], "code": r["code"], "market": r["market"],
            "quantity": qty,
            "avg_cost": avg_cost.quantize(_CENT),
            "cost": (qty * avg_cost).quantize(_CENT),
        })
    return holdings


def upgrade() -> None:
    conn = op.get_bind()

    snapshots = conn.execute(
        sa.text(
            """
            SELECT s.id, s.account_id, s.snapshot_date, s.balance,
                   a.account_type, a.household_id
            FROM account_snapshots s
            JOIN accounts a ON a.id = s.account_id
            WHERE s.data_stat_cd = :active
            ORDER BY s.snapshot_date ASC, s.account_id ASC
            """
        ),
        {"active": _ACTIVE},
    ).mappings().all()

    updated = 0
    for s in snapshots:
        as_of = _month_end(s["snapshot_date"])
        acc = s["account_id"]
        is_investment = s["account_type"] == _INVESTMENT

        cash = _cash_asof(conn, acc, as_of, investment=is_investment)

        valuation = Decimal("0")
        if is_investment:
            holdings = _asof_holdings(conn, acc, as_of)
            valuation = sum((h["cost"] for h in holdings), Decimal("0"))

            # 그 달 PVH 를 as-of 보유(원가)로 replace
            conn.execute(
                sa.text(
                    """
                    DELETE FROM portfolio_value_history
                    WHERE account_id=:acc AND snapshot_date=:sd
                    """
                ),
                {"acc": acc, "sd": s["snapshot_date"]},
            )
            for h in holdings:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO portfolio_value_history
                          (id, household_id, account_id, portfolio_item_id, snapshot_date,
                           quantity, avg_price, current_price, cost, valuation,
                           data_stat_cd, frst_reg_dt, last_mdfcn_dt)
                        VALUES
                          (:id, :hh, :acc, :item, :sd,
                           :qty, :avg, :avg, :cost, :cost,
                           :active, now(), now())
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "hh": s["household_id"], "acc": acc,
                        "item": h["item_id"], "sd": s["snapshot_date"],
                        "qty": h["quantity"], "avg": h["avg_cost"], "cost": h["cost"],
                        "active": _ACTIVE,
                    },
                )

        new_balance = (cash + valuation).quantize(_CENT)
        old_balance = _d(s["balance"]).quantize(_CENT)
        if new_balance != old_balance:
            conn.execute(
                sa.text("UPDATE account_snapshots SET balance=:b WHERE id=:id"),
                {"b": new_balance, "id": s["id"]},
            )
            updated += 1
            print(
                f"[backfill] acct={acc} {s['snapshot_date']}: "
                f"{old_balance} -> {new_balance} (delta {new_balance - old_balance})"
            )

    print(f"[backfill] done - {updated}/{len(snapshots)} snapshot rows updated")


def downgrade() -> None:
    # 데이터 백필 — 원래 balance/PVH 복원 불가하므로 no-op.
    pass
