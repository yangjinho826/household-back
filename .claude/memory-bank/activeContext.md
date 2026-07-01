# 활성 컨텍스트

## Goal

**평가금 수정 UX를 거래 화면으로 이동 + 모바일 삭제버튼 수정 + 도커 DB 포트** (2026-06-04, 자산통합 후속).

## Status

**3건 전부 완료. 미커밋 — 커밋 대기.** (`npm run build`/tsc/eslint 통과)

- **#1 모바일 삭제버튼**: `form-sheet.tsx` Drawer가 BottomTab(z-index 500, 64px) 높이 보정 누락 → 삭제버튼이 탭바 밑에 깔려 클릭 차단. `household-switcher.tsx`의 보정 공식(`maxHeight: min(90dvh, 100dvh - bottom-tab-h - safe-bottom)` / `paddingBottom: bottom-tab-h + safe-bottom + 16`) 적용.
- **#2 평가금→거래**: 거래 폼 맨 위 **통장 칩 리스트**(전체 계좌) + 선택 타입 분기. 수동자산→평가조정(새 평가액 절대값 입력, diff를 VALUATION 거래로 생성), 일반→기존 폼. `use-form.tsx`에 accounts param·txType 동기화 effect·VALUATION submit 분기 추가. **자산 폼(asset-form/use-asset-form)은 초기금(startBalance) 직접수정으로 복귀** — 자동 VALUATION 생성 제거. 백엔드 무변경(VALUATION 거래·form-options 전체계좌·account update startBalance 이미 완비).
- **#3 도커 포트**: base compose 불변, git-ignore된 `docker-compose.override.yml`로 `127.0.0.1:5432` localhost 한정 노출. `.gitignore`에 override 추가.
- **#2 후속 UX**: 거래 폼 통장 칩을 **가로 스크롤 한 줄**(통장 많을 때 대비).
- **#2 후속2 — 거래 필터 전체 통장**: 거래 탭 계좌 필터에 **전체 통장 노출**(적금/수동자산/투자 다 보임, 이동 X 탭 안 필터). 백엔드 `list_account_ledger` **타입 가드 제거**(전 타입 허용) + `_ledger_start_balance`에 `sums["valuation_net"]` 추가 → 수동자산 평가조정 running balance 정확. `_LEDGER_ACCOUNT_TYPES` 상수 삭제(+AccountType import 정리). INVESTMENT은 매매현금이 거래 테이블 밖이라 잔액 부정확 → 프론트에서 `showBalance=false`로 **잔액 컬럼만 숨김**(거래는 표시). plumbing: transactions-section→AccountLedgerView→LedgerRow. LedgerRow에 VALUATION "평가조정" 보조라벨. **백엔드 변경 → 서버 재기동 필요.**

이전 마일스톤(자산통합):
**백엔드 자산통합 + 프론트(C) 전부 완료. 커밋됨(77bb340까지).**

C(프론트) 완료 (2026-06-04):
- 백엔드 단계1: `account/enum.py` `MANUAL_ASSET_DEFAULT_META` + `create_account` 기본 color/icon 부여 (QA verified: REAL_ESTATE → #8B5CF6/building-estate)
- transaction 프론트 VALUATION 지원: `TxType`+`ValuationDirection`+`valuationDirection`, 거래폼 직접선택 제외, tx-row/ledger-row 방향별 부호·색
- account feature 통합: `asset-form.tsx`+`use-asset-form.tsx` 신규 (추가=account생성 / 평가액수정=차액 VALUATION / 이름·타입=update / 삭제)
- manual-asset feature 7파일 삭제 + queries.ts 정리. wealth-section `accounts.filter(isManualAsset)`로 전환
- 날짜 mantine v8 string화: transaction/trade/household form
- i18n: account.asset.*, COMMODITY·VALUATION 라벨, manual-asset 제거
- 검증: 백 pytest 4 green · 프론트 typecheck/lint 통과 · curl 골든패스(생성·증액·감액·지출차단·삭제) 전부 통과

이전 Status (백엔드 단계):
**백엔드 자산통합(1~6) 완료 + 커밋(`38737b0`, 테스트 제외).**

커밋됨:
- 프론트 버그3 (main): `8bbb370` 누적매매수익 날짜(mantine v8 string화), `7173a6e` 거래 후 계좌 캐시(transaction mutation에 portfolio invalidate 누락 추가), `140397f` 도넛 외/현금 pinToEnd 맨뒤 정렬
- 백엔드 (main): `38737b0` VALUATION 거래타입+valuation_direction 컬럼, 잔액 공식 통일, manual_asset 도메인 제거, 평가액→start_balance 흡수 마이그(e5f9a1c3d7b2, f1b3d5a7c9e2)

검증: dev DB(postgres-dev) `alembic upgrade head` 적용 완료(head=f1b3d5a7c9e2). pytest 4 green(단, `tests/`+`pyproject.toml` pytest설정은 미커밋 — 테스트 제외 지시).

## Context

- **C(프론트) 핵심 복잡성**: account create가 수동자산 type 생성 시 color/icon/이름 기본부여를 떠안아야 함. 기존 `manual_asset._ROLLUP_ACCOUNT_META` 값: REAL_ESTATE=`#8B5CF6`/`building-estate`, PENSION=`#EC4899`/`pig-money`, COMMODITY=`#F59E0B`/`coin`, SAVINGS_ASSET=`#10B981`/`wallet`. → 백엔드 account 도메인 보강 필요.
- 프론트 `_features/manual-asset/` (api/queries/components/form/hooks/types) + 사용처(wealth-section, transaction/form, account/types, _constants/queries, ko·en messages) 13+파일 → account 생성 + 평가조정 거래로 재구성.
- **평가액 수정 UX**: "현재 총 평가액" 절대값 입력 → (새값 − 현재잔액) 차액을 VALUATION 거래로 자동 생성. 이체는 기존 그대로 별도.
- VALUATION API: `POST /transactions` `{tx_type:"VALUATION", amount(양수), valuationDirection:"INCREASE"|"DECREASE", accountId(수동자산 통장)}`. 수동자산 통장에만 허용.
- trade-form/transaction form/household form 날짜도 mantine v8 버그(`value={dayjs(x).toDate()}` Date 전달) — C에서 같이 string 규격화.
- 잔액 공식(백엔드): 전 분류 `start_balance + 거래합`. `_cash_flow`에 `valuation_net` 포함. `_calc_balance`/`_build_balance` 동일성 유지(test_account_balance.py).

## Next Step

1. **커밋** — 백엔드(account 기본 메타) + 프론트(자산통합 C) 분리 커밋. 백엔드 `tests/`+`pyproject` pytest설정 커밋 여부 결정.
2. dev→main 머지 검토 (R5a 사이클 + 자산통합 전부 완료).
3. (선택) 브라우저 E2E — 자산 추가/평가액 수정 폼 실제 렌더 (Windows headless 빌드 필요 시).
