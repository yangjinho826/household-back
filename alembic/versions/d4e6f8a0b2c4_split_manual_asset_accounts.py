"""수동자산 전용계좌 1:1 분리

rollup 공유(asset_class당 통장 1개) → 자산마다 전용통장(name=자산명).
이체로 자산별 잔액을 분리 추적하기 위함. 기존 이체 0건이라 잔액 무손실.

각 공유 통장에 묶인 수동자산들을:
- 1개면: 공유 통장을 그 자산 전용으로 승격(통장명 → 자산명).
- N개면: 첫 자산은 기존 통장 재사용(이름 변경) + 나머지는 전용 통장 신규 생성 후 재연결.

downgrade 는 이체 거래가 묶여 역분리가 위험하므로 no-op.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e6f8a0b2c4"
down_revision: Union[str, Sequence[str], None] = "c3d5e7f9a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MANUAL_TYPES = ("REAL_ESTATE", "PENSION", "COMMODITY")


def upgrade() -> None:
    conn = op.get_bind()

    rollups = conn.execute(
        sa.text(
            """
            SELECT id, household_id, account_type, color, icon
            FROM accounts
            WHERE account_type IN ('REAL_ESTATE', 'PENSION', 'COMMODITY')
              AND data_stat_cd = '50'
            """
        )
    ).mappings().all()

    for r in rollups:
        assets = conn.execute(
            sa.text(
                """
                SELECT id, name FROM manual_assets
                WHERE account_id = :aid AND data_stat_cd = '50'
                ORDER BY frst_reg_dt ASC
                """
            ),
            {"aid": r["id"]},
        ).mappings().all()
        if not assets:
            continue

        # 첫 자산 — 기존 공유 통장을 전용으로 승격 (이름만 자산명으로)
        conn.execute(
            sa.text("UPDATE accounts SET name = :n WHERE id = :id"),
            {"n": assets[0]["name"], "id": r["id"]},
        )
        if len(assets) == 1:
            continue

        # 나머지 자산 — 전용 통장 신규 생성 후 manual_assets 재연결
        max_sort = conn.execute(
            sa.text(
                "SELECT COALESCE(MAX(sort_order), 0) FROM accounts "
                "WHERE household_id = :hid"
            ),
            {"hid": r["household_id"]},
        ).scalar()

        for offset, a in enumerate(assets[1:], start=1):
            new_id = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    """
                    INSERT INTO accounts
                      (id, household_id, name, account_type, start_balance,
                       color, icon, sort_order, is_archived, data_stat_cd,
                       frst_reg_dt, last_mdfcn_dt)
                    VALUES
                      (:id, :hid, :name, :atype, 0,
                       :color, :icon, :sort, false, '50',
                       now(), now())
                    """
                ),
                {
                    "id": new_id,
                    "hid": r["household_id"],
                    "name": a["name"],
                    "atype": r["account_type"],
                    "color": r["color"],
                    "icon": r["icon"],
                    "sort": max_sort + offset,
                },
            )
            conn.execute(
                sa.text(
                    "UPDATE manual_assets SET account_id = :acc WHERE id = :aid"
                ),
                {"acc": new_id, "aid": a["id"]},
            )


def downgrade() -> None:
    # 분리된 통장을 다시 합치면 이체 거래가 엉키므로 no-op.
    pass
