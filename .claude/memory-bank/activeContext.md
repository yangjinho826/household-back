# 활성 컨텍스트

## Goal

**household-back 코드베이스 분석 가이드 (입문자용 코드 산책)** (2026-06-18 시작). 17개 도메인 + core 인프라를 **FastAPI 처음 보는 주니어 개발자**가 혼자 읽을 수 있게 도메인별로 쉽게 풀어낸 마크다운 시리즈를 `docs/codewalk/` 에 작성. 코드는 변경 X (순수 분석 문서). 이직 포폴/온보딩 자산. `docs/testing/` 트랙의 자매격.

## Status

**배치1·2 완료** — `docs/codewalk/`:
- 배치1: `README.md` · `00-overview.md` · `01-core-infra.md`
- **배치2 (방금 완료, 톤 검수 통과 후)**:
  - `02-auth-user-household.md` (회원가입≠가계부생성 · access(body)+refresh(HttpOnly쿠키) · refresh 5개제한 · /refresh 2단검증(JWT+DB) · CurrentHousehold=X-Household-Id+멤버십 HH001 · owner 멤버 자동등록)
  - `03-account.md` (잔액=저장X 계산값 · 타입8종→공식3그룹(일반/수동자산/투자) · _calc_balance · is_archived≠soft-delete · cascade 삭제 순서 · 목록 배치로드 N+1차단)

배치2 Explore 정밀수집 + 핵심코드 직접확인(deps.py·service.py·router.py) 거침. **계획파일: `~/.claude/plans/spicy-herding-zebra.md`**.

## Context

- **9개 문서 구조**: 00 overview / 01 core / 02 auth·user·household / 03 account / 04 category·transaction / 05 fixed·snapshot / 06 portfolio-trading / 07 pricing·snapshot·wealth / 08 home·stats·settings.
- **공통 7섹션 템플릿**: ①한마디 ②개념 콕 ③데이터 모델 ④핵심 로직 코드리딩(대표흐름만 깊게) ⑤API 표 ⑥데이터 흐름 ⑦꼭 기억할 규칙.
- **검증된 코드 사실** (codex+직접확인): ORM relationship 0개(논리FK+서비스검증, transaction만 ForeignKey 2개) / market_price·exchange_rate 라우터 미등록(내부·배치 전용) / 스케줄러 5잡(환율·국장·미장·멱등cleanup·월간스냅샷) / is_archived≠soft-delete / CurrentHousehold=X-Household-Id 헤더 / root_path="/api"+prefix=실제URL / alembic/versions 22개.
- **사실 근거 우선순위**: 1차=model.py+alembic/versions, router.py, service.py / 보조(불일치 가능)=ddl/init.sql, docs/api-list.md / 설계의도 참고=decisions.md.
- **진행 방식**: 영역별 배치로 끊어가며. 배치1 후 톤 합의 → 02~08 반영.
- 도메인 규모: portfolio 2216 · transaction 1418 · account 859 · household 701 · fixed 595 · category 521 · account_snapshot 475 · core 1300줄.

## Next Step

1. **배치3** — `04-category-transaction.md` (카테고리 + 거래: 수입/지출/이체 양방향 · income/expense/transfer 합계가 account 잔액에 반영되는 흐름 · VALUATION) + `05-fixed-snapshot.md` (고정지출 메타 + 스케줄러 월간 스냅샷). 영역 코드 Explore 정밀수집 → 입문자 톤 작성 → file:line 교차확인.
2. 배치4~5 순차 (06·07 → 08).
3. 03-account 에서 "거래합(sum_for_account)" 으로 미룬 부분(income/expense/transfer_out/transfer_in/valuation_net 실제 적재)을 04에서 받아 설명.
