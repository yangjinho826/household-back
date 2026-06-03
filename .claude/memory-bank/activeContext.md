# 활성 컨텍스트

## Goal

**가계부 × 자산 통합 — 월별 자산변동 추적** (총자산 기준, 부채/순자산 안 함).
직전 사이클 R5a(asset_class 배분 + ManualAsset) 완료. 이번 작업: **삭제 정책 개편 + codex 백엔드 QA 버그 일괄 수정**.

## Status

**브랜치 `feat/delete-policy-cascade` — 백엔드 16파일 + tests/ 신규, 프론트 6파일. 커밋 진행 중, push 안 함. pytest 13 green.**

완료:
- 통장 삭제: 차단→cascade soft-delete(D안 — 이체 상대 살아있으면 행 보존, 보유종목만 차단, 단독거래/수동자산/종목이력/스냅샷 cascade)
- 카테고리 삭제: 차단 제거, category_id 유지
- 프론트 무알림 6곳: 삭제 모달 onConfirm try/catch + getErrorMessage red 토스트
- codex QA 7개: PATCH 이체 깨짐 / fixed_expense_id 검증 / 카테고리 kind 정합성 / 종목 재계산 스킵 / 수동자산 cascade / 계좌 N+1 배치화 / bcrypt async offload
- stats 회귀: 삭제 카테고리 거래 by_category 누락 fix(find_by_ids)

## Context

- **이체 D안 핵심**: 통장 삭제 시 이체 행을 남겨 살아있는 상대통장 잔액·통계 보존. `soft_delete_transfers_with_dead_counterparty`는 양쪽 다 DELETED인 이체만 삭제. 통장 본체 죽이기 전에 실행해야 자기 자신 오판 방지.
- **N+1 배치화 안전망**: `_load_balance_sources`(4쿼리) + `_build_balance`. 단건 `_calc_balance`는 유지. `test_account_balance.py`가 list==detail 동일성 검증(cash/투자/수동자산).
- **테스트 인프라 신규**: aiosqlite in-memory(StaticPool), `tests/conftest.py` 시드 헬퍼. `func.extract` 쓰는 stats 쿼리는 sqlite 비호환이라 stats 테스트는 미작성.
- 노션 API 레퍼런스 79개 기록: Private메모DB/대분류=개인/중분류=Household.

## Next Step

1. 이번 브랜치 커밋 마무리(feat 삭제정책 / fix codex / perf / test 분리) + 메모리 커밋.
2. 프론트 무알림 6곳 커밋.
3. PR → main 머지 검토.
