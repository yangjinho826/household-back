# 활성 컨텍스트

## Goal

**household-back 코드베이스 분석 가이드 (입문자용 코드 산책)** (2026-06-18 시작). 17개 도메인 + core 인프라를 **FastAPI 처음 보는 주니어 개발자**가 혼자 읽을 수 있게 도메인별로 쉽게 풀어낸 마크다운 시리즈를 `docs/codewalk/` 에 작성. 코드는 변경 X (순수 분석 문서). 이직 포폴/온보딩 자산. `docs/testing/` 트랙의 자매격.

## Status

**배치1·2·3 완료** — `docs/codewalk/`:
- 배치1: `README.md` · `00-overview.md` · `01-core-infra.md`
- 배치2: `02-auth-user-household.md` · `03-account.md`
- 배치3: `04-category-transaction.md`(거래 5종·이체 한줄·sum_for_account·러닝밸런스·카테고리 orphan) + `05-fixed-snapshot.md`(고정지출 메타·월간 박제 catch-up/upsert·hard vs soft delete·스케줄러 5잡) — 둘 다 신규 7섹션 틀. 사용자 검수 04 생략(d), 05 미검수.

**★ 형식 전환 (2026-06-19)**: 사용자 요구 "소스를 더 딥하게 — API 단위 추적"으로 **도메인 7섹션 틀 개편**. §4 "공통 메커니즘"(여러 API 공유 로직 1번 깊게) + §5 "엔드포인트별 풀 트레이스"(API마다 요청→의존성·검증→서비스→repo쿼리→응답조립→commit, file:line). 공통은 §5에서 `→ §4-x` 참조해 반복 제거. 02(API 16개)·03(API 6개) 이 틀로 **재작업 완료**, 사용자 03 형식 검수 통과. README 공통구성도 신규 틀로 갱신. 계획파일: `~/.claude/plans/drifting-crafting-anchor.md` (이전: `spicy-herding-zebra.md`).

## Context

- **9개 문서 구조**: 00 overview / 01 core / 02 auth·user·household / 03 account / 04 category·transaction / 05 fixed·snapshot / 06 portfolio-trading / 07 pricing·snapshot·wealth / 08 home·stats·settings.
- **공통 7섹션 템플릿 (신규)**: ①한마디 ②개념 콕 ③데이터 모델 ④**공통 메커니즘**(공유 로직 1번 깊게) ⑤**엔드포인트별 풀 트레이스**(API마다 요청→응답 한 줄기, 메인) ⑥데이터 흐름(큰 그림) ⑦꼭 기억할 규칙. (구버전 "④핵심로직+⑤API표"는 폐기 — 배치3~5도 신규 틀로.)
- **검증된 코드 사실** (codex+직접확인): ORM relationship 0개(논리FK+서비스검증) / **transaction 실제 ForeignKey 1개뿐 = fixed_expense_id(→fixed_expenses.id, ondelete SET NULL); account_id·to_account_id·category_id 는 논리FK** (근거: ddl/init.sql 전부 logical FK 주석 + alembic b5375d2ae3a6 가 fk_transactions_fixed_expense_id 만 추가. model.py:32 일치. ※구 메모 "ForeignKey 2개"는 오류였음 — 정정) / market_price·exchange_rate 라우터 미등록(내부·배치 전용) / 스케줄러 5잡(환율·국장·미장·멱등cleanup·월간스냅샷) / is_archived≠soft-delete / CurrentHousehold=X-Household-Id 헤더 / root_path="/api"+prefix=실제URL / alembic/versions 22개.
- **사실 근거 우선순위**: 1차=model.py+alembic/versions, router.py, service.py / 보조(불일치 가능)=ddl/init.sql, docs/api-list.md / 설계의도 참고=decisions.md.
- **진행 방식**: 영역별 배치로 끊어가며. 배치1 후 톤 합의 → 02~08 반영.
- 도메인 규모: portfolio 2216 · transaction 1418 · account 859 · household 701 · fixed 595 · category 521 · account_snapshot 475 · core 1300줄.

## Next Step

1. **배치4** — `06-portfolio-trading.md` (최대 도메인 2216줄: 주식 매매 BUY/SELL · PortfolioItem 보유종목 · PortfolioValueHistory 종목 평가액 박제 · 03 §4-2 INVESTMENT 잔액공식=현금+보유평가액 완결) + `07-pricing-snapshot-wealth.md` (market_price·exchange_rate 시세/환율 내부배치 · wealth 자산배분추이). 신규 7섹션 틀.
2. 배치5 — `08-home-stats-settings.md`.
3. (완결된 약속) 03 "거래합" → 04 §4-2 / 03 §4-5 "박제 과거" → 05 §4-2 / 04 §4-1 "FIXED_EXPENSE·종목 평가액 박제" → 05 §4-1·§4-2(종목은 06으로 다시 미룸).
