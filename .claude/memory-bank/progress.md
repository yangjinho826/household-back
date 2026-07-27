# 진행 상태

## 완료
- [ ] 초기 셋업
- [x] 2026-07-27: SRE 로드맵 1번 C fault-injection — `tests/idempotency/test_crash_window.py` **3 케이스 통과**(C1 예외주입 / C2·C3 state-based sim), 멱등성 커버리지 92%→**97%**, 소스 무수정(자백 목적). **핵심 실측: C1 이 A9 와 갈림** — 라우터 성공 후 미들웨어 예외는 거래 1건이 남는다(A9 은 0건) → `call_next` 반환 시점에 `get_db` 커밋이 이미 끝났다는 직접 증거 = crash window 실재. C3 = TTL 만료 후 재시도 시 **거래 2건** → exactly-once 아님 확정. codex 지적 반영: 용어를 fault injection(C1만)/state-based simulation(C2·C3)으로 분리, 나머지 crash 지점 4개는 최종 상태가 C1·C2 로 **수렴**함을 논증해 기각, 면접 반격 4개는 `SCENARIOS.md` 표로 보관.
- [x] 2026-07-27: SRE 로드맵 1번 B advisory lock — `tests/scheduler/test_advisory_lock.py` **8 케이스 통과**(B1/B1-nc/B2/B3/B4/B4-nc/B5 + codex 지적으로 신설한 **B6 동시 `run_locked_job` 경합**). 락 로직 커버리지 100%(미커버는 cron 등록부), **소스 결함 0**. codex 3건 중 2건 채택(pg_backend_pid 단언·B6), 1건 기각(B3/B4 중복). nc 용어를 "역증명"→"대조군"으로 정정 — A11-nc(보호 제거 → N건)와 달리 B 의 nc 는 상수 오작동 배제까지만.
- [x] 2026-07-27: SRE 로드맵 1번 ① 시나리오 + A 멱등성 — `tests/SCENARIOS.md`(공개계약 도출, codex 교차검증 2건 반영) + `tests/fixtures/factory.py`(seed 후 commit) + `tests/idempotency/` **14 케이스 통과**(A1~A12 + A11/A11-nc 동시성 대조: 1건 vs N건). 멱등성 코어 커버리지 92%, **소스 결함 0**(초기 실패 2건은 테스트 하니스 문제). 면접 미끼: A10 경로 실체(글로벌 핸들러가 미들웨어 바깥)·4xx 캐싱 계약.
- [x] 2026-07-24: SRE 로드맵 1번 ⓪ 테스트 실험실 구축 — docker-compose.test(PG17 tmpfs 55432) + .env.test + conftest(env 선주입 → `metadata.create_all` → 매 테스트 TRUNCATE → ASGITransport client) + smoke 3/3 통과. 계획의 `alembic upgrade head` 는 빈 baseline 때문에 `create_all` 로 정정. 노션 "Phase 1 진행기록" 페이지 개설(https://app.notion.com/p/3a7a6161032981bd8f8bf4f4196584ac) + 누적 정리 규칙 메모리화.
- [x] 2026-07-03: docs/codewalk 배치5 (마지막) — 08-home-stats-settings(home·stats·settings 셋 다 테이블없는 조회/집계 도메인·GET 3개·home 위임집계·stats 3단집계+ratio·삭제카테고리 보존·settings count×5) + README 진행현황/문서표 전체 갱신. **시리즈 9개 문서 완결.** 신규 7섹션 틀, file:line 전수 대조.
- [x] 2026-06-26: docs/codewalk 배치4 — 06-portfolio-trading(17엔드포인트 6그룹·평단 replay·실현손익 박제) + 07-pricing-snapshot-wealth(환율/시세 내부배치·환율→시세 순서의존·wealth 박제 소비처). 신규 7섹션 틀, file:line 전수 대조. 미검수 묶음 커밋.
- [x] 2026-06-19: docs/codewalk 형식 전환 — 도메인 7섹션 틀 개편(§4 공통 메커니즘 + §5 엔드포인트별 풀 트레이스, file:line). 02(API16)·03(API6) 재작업 + README 갱신. 사용자 "소스 더 딥하게" 요구 반영. 계획: ~/.claude/plans/drifting-crafting-anchor.md
- [x] 2026-06-18: docs/codewalk 배치2/5 — 02-auth-user-household(인증/세대/CurrentHousehold) + 03-account(잔액=계산값/타입8종/is_archived). 톤 검수 통과 후 작성. Explore 정밀수집 + 핵심코드 직접확인.
- [x] 2026-06-18: docs/codewalk 코드분석 가이드 착수 — README(목차)+00-overview+01-core-infra (배치1/5). FastAPI 입문 주니어 대상, codex 교차리뷰 반영. 계획: ~/.claude/plans/spicy-herding-zebra.md
- [x] 2026-06-03: 통장/카테고리 삭제 정책 개편 (통장 cascade soft-delete D안 + 카테고리 차단 제거) + 프론트 무알림 6곳 fix + stats 회귀 fix
- [x] 2026-06-03: codex 백엔드 전체 QA 7개 수정 (PATCH 이체 깨짐 / fixed_expense_id 검증 / 카테고리 kind / 종목 재계산 스킵 / 수동자산 cascade / 계좌 N+1 배치화 / bcrypt async) + 테스트 13개

## 진행 중
- [ ] 2026-07-24: SRE 로드맵 1번 — 테스트 스위트 + CI 게이트. **⓪ 환경 + ① 시나리오 + A(14) + B(8) + C(3) 완결 — 전체 28 passed**, 다음 **D 도메인 🔴 4~5개** → ④ CI 2중 게이트(ci.yml+deploy) → ⑥ 포폴 X 채움. 계획: `~/.claude/plans/drifting-knitting-corbato.md`. 스키마 소스는 `create_all`(빈 alembic baseline). 각 단계 완료 시 노션 Phase1 진행기록 페이지에 누적 정리(규칙 메모리화).

## 막힘
- [x] 2026-06-04: 평가금 수정 거래화면 이동(통장 칩+타입분기) + 모바일 삭제버튼 z-index 수정 + 도커 DB 포트 override
