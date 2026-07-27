# 활성 컨텍스트

## Goal

**이직 포폴 "운영 강점" 카드화 + SRE 로드맵 실행** (2026-07-21 시작). household-back 을 이력서/포폴에 추가 — 포지션은 "저비용 단일 서버를 운영 가능한 상태로 만드는 운영 감각" 보조 카드 (트래픽 카드 아님, codex 2회 교차검증). 포폴 본문은 `carrer/portfolio/household-back.md`, 이력서 블록은 `carrer/resume/household-이력서-블록.md`, 구현 로드맵은 이 레포 `docs/portfolio-sre-roadmap.md`. (직전 트랙: codewalk 시리즈 9개 문서 완결 — 2026-07-03 종료.)

## Status

**로드맵 1번 A~C + D2 + D1 완결 (2026-07-27) — 전체 37 passed(멱등성 14+3 / 스케줄러 8 / smoke 3 / 도메인 9), 멱등성 97% · 락 로직 100%. D2 에서 A~C 최초의 진짜 소스 결함 발견·수정, D1 은 예측대로 GREEN. 다음 ④ CI 2중 게이트.**

**D1 계좌 원장 running balance (`tests/domain/test_account_ledger.py`, 5 케이스 전부 GREEN, 소스 결함 0)**: 불변식 5개를 docstring 에서 도출 — A 닫힘(끝까지 순회 시 마지막 행 `balance_after − signed_amount == start_balance`) / B 페이지 불변(`limit=100` 1페이지 == `limit=2` 3페이지) / C 월 기준점(다음 달 거래 추가해도 당월 잔액 불변) / D 이체 부호(출금 −, 입금 +) / E 평가조정 부호(INCREASE +, DECREASE −). **착수 전 코드 독해로 GREEN 을 예측했고 그대로 나왔다** — D2 와 같은 "값을 두 곳에서 계산" 구조지만 `_signed_amount`(service.py:422) 와 `sum_for_account`(repository.py:185) 의 부호 규칙이 일치하고, 조회/합산 필터도 `or_(account_id, to_account_id)` 로 대칭이라 안 갈렸다. **결함을 가른 건 구조가 아니라 두 경로가 같은 순서·같은 규칙을 보는가** — D2 는 입력순서 vs `tx_date asc` 로 갈렸다(면접 대비 대비 카드). D1-2 에 **페이지 수 단언**(`paged_pages == 3`)을 넣어 커서가 한 페이지만 돌고도 통과하는 구멍을 막음. 계획: `~/.claude/plans/d1-snug-newt.md`. 미착수 엣지: D1-6 깨진 커서 fallback(`service.py:447,450-451`).

**D2 포트폴리오 실현손익 (`tests/domain/test_portfolio_pnl.py`, 4 케이스)**: 도출 불변식 = "활성 거래 집합이 같으면 realized_pnl·quantity·avg_price 는 재계산 트리거 시점과 무관하게 같다". D2-1(매도 후 재매수 평단)·D2-2(과거 BUY 수정 → SELL 재박제) GREEN, **D2-3·D2-4 RED**. 결함 = **진실 원천 2개** — `buy()`/`sell()` 은 incremental(입력 순서, 그 순간 `item.avg_price`)인데 `_recompute_realized_pnl()` 은 replay(`tx_date asc`, `repository.py:236`). 백데이팅 매수(매도보다 앞선 날짜를 뒤늦게 입력) 시 갈리고, **금액과 무관한 memo 수정 한 번**이 저장값을 뒤집었다(실현손익 25,000 → 0 / 평단 1,666.67 → 1,500). **수정**: buy/sell incremental 제거 → `_recalc_item_from_transactions`(replay) 통일, sell 사전 `realized_pnl` 박제 제거, 전량매도 판정을 replay 결과(`item.quantity == 0`) 기준으로. C 와 달리 **자백 아닌 수정** — 고치는 비용이 한 줄이라 "알고도 안 고쳤다"가 성립 안 함. **D3(IDOR) 강등**: 착수 전 `app/domain/*/service.py` public 함수 전수 스캔 → `find_by_id` 후 소속 검증 누락 0건(user 도메인만 예외 = 멤버 초대용 설계 선택, 라우터에 "인증 가드용" 주석 명시). C 핵심 실측: 라우터 성공 후 미들웨어 예외는 **거래 1건이 남는다**(A9 은 0건) → `call_next` 반환 시점에 `get_db` 커밋이 이미 끝났다는 직접 증거 = crash window 실재. C3 는 TTL 만료 후 재시도 시 **거래 2건** → exactly-once 아님 확정. codex 반영: 용어를 fault injection(C1)/state-based simulation(C2·C3)으로 분리, 다른 crash 지점 4개는 최종 상태가 C1·C2 로 수렴함을 논증해 기각, 면접 반격 4개는 `SCENARIOS.md` 표로 보관. B 는 codex 교차검증 3건 중 2건 채택 — `pg_backend_pid()` 상이 단언(독립 커넥션 자립 증명) + **B6 동시 `run_locked_job` 경합**(계약 "다중 워커 동시 진입 시 1개만" 직접 검증, `asyncio.Event` 로 순서 고정해 flaky 제거). nc 용어 정정: A11-nc(보호 제거 → N건)만 역증명, B 의 nc 2개는 상수 오작동 배제 **대조군**. 테스트 0개 → **명세 기반 사후검증**(소스 이미 있음, TDD 신규작성 아님). 계획: `~/.claude/plans/drifting-knitting-corbato.md`. 확정 결정: 실 PG(docker-compose.test) / 스키마 소스 **`Base.metadata.create_all`**(계획의 `alembic upgrade head` 는 이 레포 baseline 이 빈 마이그레이션이라 스키마 0개 생성 → 정정. decisions.md 참조) / 매 테스트 **TRUNCATE**(동시성 때문에 tx-rollback 불가) / **negative control 역증명**(결과 1건만으론 순차와 구분불가 → 락 우회 버전이 N건 만드는 걸 동일 하니스로 대조) / CI **ci.yml+deploy 게이트 둘 다** / 도메인 통합 D는 **🔴 4~5개만**. codex 순서 교차검증 시도 → 이 환경서 긴 프롬프트 hang("OK" 11초는 되나 4질문 분석은 5분+ timeout, 3회) → **자체 ultrathink 로 4질문 대체 검증**: 순서 타당하나 ⓪smoke·⑤CI 명시 추가, ASGITransport 동시성은 진짜 경합 성립(진짜 PG+독립세션+gather)이나 negative control 없으면 극장.

**핵심 제약**: 멱등성 미들웨어가 `async_session()` 직접 사용(DI 아님) → dependency_overrides 로 못 바꿈 → conftest 최상단서 `os.environ` 테스트 PG 주입 **후** 앱 import (config/database 가 import 시점 engine 생성). 멱등성 실증 엔드포인트 = `POST /transaction/create`(user→household→membership→account→category factory 필요).

**(이전 마일스톤) 로드맵·포폴 초안 (2026-07-21) + 노션 재료 (2026-07-22).** 포폴 6카드, 검증 숫자: 도메인 17 / 마이그레이션 22 / 태그 배포 18회 / 잡 5개 / AI 로그 183건. realized_pnl 백필 회고 반영(codex 3차 통과). "운영 성과" ❌ → "운영 준비도·체계" ✅ 톤. nginx 502 건 제외(미적용 상태).

## Context

- **로드맵 순서**: 1 테스트+CI 게이트(실 PostgreSQL 필수, 멱등성 asyncio.gather 동시 N발 + advisory lock 경쟁 + 선택 fault-injection) → 2 주간 자동 복구 리허설(RTO 실측) → 3 장애 알림(잡/백업/배포/헬스체크 webhook) → 4 migration playbook(expand-contract) → 실증: compose 앱 2개 다중 인스턴스 멱등성. 옵션: 용량 한계 실측·오버헤드·무중단 배포. 상세·확정 판단 표는 `docs/portfolio-sre-roadmap.md`.
- **핵심 제약 (재논의 X)**: k6 절대 처리량 폐기 / 멀티스레드 클라이언트 무의미(단일 이벤트 루프) / 멱등성 주장은 "동시 in-flight 중복 방지"까지 — crash window(비즈니스 커밋 후 COMPLETED 전 죽음)는 포폴에 안 쓰고 면접 미끼 / "exactly-once·무장애" 표현 금지.
- 현재 테스트 0개 (main에도 없음) — 이게 최대 구멍이라 1순위.
- 브랜치: `docs/portfolio-sre-roadmap`.

## Next Step

1. ~~**⓪ 환경**~~ **완료**(smoke 3/3). ~~**① SCENARIOS.md + factory.py + A 멱등성**~~ **완료**(14 케이스, A1~A12 + A11/A11-nc 대조, 커버리지 92%). codex 교차검증 반영(A11-nc 재설계·A12 4xx 캐싱). 소스 결함 0, 면접 미끼 2개(A10 경로 실체·4xx 캐싱).
2. ~~**B advisory lock**~~ **완료**(8 케이스). ~~**C fault-injection**~~ **완료**(3 케이스, `test_crash_window.py`, 계획 `~/.claude/plans/c-dazzling-flamingo.md`). ~~**D2 realized_pnl**~~ **완료**(4 케이스, 결함 1건 수정). ~~**D1 ledger running balance**~~ **완료**(5 케이스 전부 GREEN, 계획 `~/.claude/plans/d1-snug-newt.md`). **다음: ④ CI 2중 게이트** — `ci.yml`(push/PR) + `deploy.yml` 테스트 게이트. D 잔여는 선택: D3 IDOR(회귀 안전망) / D4 종목 상태 전이 / D1-6 깨진 커서 fallback.
3. **④ RED 분석·수정** → **⑤ CI**(ci.yml + deploy 게이트) → **⑥ 포폴 X 채움**(A11/A11-nc 대조 결과 = "동일 키 동시 N건 → 1건" 실측 확정).
4. 이후 로드맵 2→3→4→실증. 완성 후: JD + AI 셀프리뷰 3프롬프트 + 면접 대본 — `carrer/interview/`.

**노션 누적 정리 규칙**: phase1 각 단계 완료 시 다시 지시 없어도 노션 "Phase 1 진행기록"(https://app.notion.com/p/3a7a6161032981bd8f8bf4f4196584ac) 에 `## NN.` 섹션 이어붙임. 규칙 상세는 harness 메모리 `phase1-notion-worklog`.
