# 활성 컨텍스트

## Goal

**가계부 × 자산 통합 — 월별 자산변동 추적** (총자산 기준, 부채/순자산 안 함).
현재 사이클: **R5a — 자산성격(asset_class) 배분 + 부동산·연금(ManualAsset) + 월별 배분추이**.

상세 계획·실행가이드는 **front 레포 `.claude/memory-bank/R5a-plan.md`** (단일 정본).

## Status

R1~R4 dev 커밋 완료(back ~a3c9afb). dev→main 머지 안 함.

**R5a-1 (asset_class + 현재 배분) 백엔드 완료, 미커밋**:
- `portfolio/enum.py` AssetClass · `portfolio/model.py` asset_class 컬럼
- 마이그레이션 A `b8e4d1a09c37_add_portfolio_asset_class` (Revises a3f7c9d2e1b8, 백필 없음 전부 STOCK)
- `enum/service.py` dispatch · `portfolio/schema.py`·`service.py` 반영
- `wealth/service.py _build_allocation` + `wealth/schema.py` AssetClassSlice/AllocationResponse
- 검증: 마이그레이션 가역성 OK · 9001 QA `wealth/overview.allocation` 정상

⬜ R5a-2 ManualAsset 도메인 / ⬜ R5a-3 asset_class_snapshots — `R5a-plan.md` 참조.

## Context

- **2축 분리**: market(거래소) 유지 + asset_class(STOCK/BOND/COMMODITY/CASH/REAL_ESTATE/PENSION/OTHER) 신규. 가격 갱신은 `market_price/service.py`가 market 축만 사용 → asset_class 무관.
- 총자산 = `Σ account.balance`(home/wealth service), 추이 = `Σ account_snapshot.balance`. 모든 자산은 계좌 roll-up으로 집계에 들어옴.
- R5a-2 통합점: `account/service.py:46` `_calc_balance`에 ManualAsset 계좌 분기. R5a-3 통합점: `account_snapshot/service.py:133` 직후 `snapshot_household_allocation`.
- codex 함정: carry-forward/as-of, historical truth, double counting, aggregation loss → `R5a-plan.md`.
- **로컬 DB 항상 `alembic upgrade head`** 선행. head = `b8e4d1a09c37`.

## Next Step

1. R5a-1 커밋 (back).
2. R5a-2 착수 — ManualAsset (`R5a-plan.md` R5a-2 섹션).
3. R5a-3 → dev→main 머지 검토.
