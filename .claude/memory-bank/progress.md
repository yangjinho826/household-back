# 진행 상태

## 완료
- [ ] 초기 셋업
- [x] 2026-07-24: SRE 로드맵 1번 ⓪ 테스트 실험실 구축 — docker-compose.test(PG17 tmpfs 55432) + .env.test + conftest(env 선주입 → `metadata.create_all` → 매 테스트 TRUNCATE → ASGITransport client) + smoke 3/3 통과. 계획의 `alembic upgrade head` 는 빈 baseline 때문에 `create_all` 로 정정. 노션 "Phase 1 진행기록" 페이지 개설(https://app.notion.com/p/3a7a6161032981bd8f8bf4f4196584ac) + 누적 정리 규칙 메모리화.
- [x] 2026-07-03: docs/codewalk 배치5 (마지막) — 08-home-stats-settings(home·stats·settings 셋 다 테이블없는 조회/집계 도메인·GET 3개·home 위임집계·stats 3단집계+ratio·삭제카테고리 보존·settings count×5) + README 진행현황/문서표 전체 갱신. **시리즈 9개 문서 완결.** 신규 7섹션 틀, file:line 전수 대조.
- [x] 2026-06-26: docs/codewalk 배치4 — 06-portfolio-trading(17엔드포인트 6그룹·평단 replay·실현손익 박제) + 07-pricing-snapshot-wealth(환율/시세 내부배치·환율→시세 순서의존·wealth 박제 소비처). 신규 7섹션 틀, file:line 전수 대조. 미검수 묶음 커밋.
- [x] 2026-06-19: docs/codewalk 형식 전환 — 도메인 7섹션 틀 개편(§4 공통 메커니즘 + §5 엔드포인트별 풀 트레이스, file:line). 02(API16)·03(API6) 재작업 + README 갱신. 사용자 "소스 더 딥하게" 요구 반영. 계획: ~/.claude/plans/drifting-crafting-anchor.md
- [x] 2026-06-18: docs/codewalk 배치2/5 — 02-auth-user-household(인증/세대/CurrentHousehold) + 03-account(잔액=계산값/타입8종/is_archived). 톤 검수 통과 후 작성. Explore 정밀수집 + 핵심코드 직접확인.
- [x] 2026-06-18: docs/codewalk 코드분석 가이드 착수 — README(목차)+00-overview+01-core-infra (배치1/5). FastAPI 입문 주니어 대상, codex 교차리뷰 반영. 계획: ~/.claude/plans/spicy-herding-zebra.md
- [x] 2026-06-03: 통장/카테고리 삭제 정책 개편 (통장 cascade soft-delete D안 + 카테고리 차단 제거) + 프론트 무알림 6곳 fix + stats 회귀 fix
- [x] 2026-06-03: codex 백엔드 전체 QA 7개 수정 (PATCH 이체 깨짐 / fixed_expense_id 검증 / 카테고리 kind / 종목 재계산 스킵 / 수동자산 cascade / 계좌 N+1 배치화 / bcrypt async) + 테스트 13개

## 진행 중
- [ ] 2026-07-24: SRE 로드맵 1번 — 테스트 스위트 + CI 게이트. **⓪ 환경 완료(smoke 3/3)**, 다음 ① SCENARIOS.md → factory.py → ② A 멱등성(A11 동시성 + negative control)/advisory B/fault C/도메인핵심 D(🔴 4~5개) → ④ CI 2중 게이트(ci.yml+deploy). 계획: `~/.claude/plans/drifting-knitting-corbato.md`. 스키마 소스는 `create_all` 로 확정(빈 alembic baseline). 각 단계 완료 시 노션 Phase1 진행기록 페이지에 누적 정리(규칙 메모리화).

## 막힘
- [x] 2026-06-04: 평가금 수정 거래화면 이동(통장 칩+타입분기) + 모바일 삭제버튼 z-index 수정 + 도커 DB 포트 override
