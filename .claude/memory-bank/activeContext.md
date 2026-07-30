# 활성 컨텍스트

## Goal

**이직 포폴 "운영 강점" 카드화 + SRE 로드맵 실행** (2026-07-21 시작). household-back 을 이력서/포폴에 추가 — 포지션은 "저비용 단일 서버를 운영 가능한 상태로 만드는 운영 감각" 보조 카드 (트래픽 카드 아님, codex 2회 교차검증). 포폴 본문은 `carrer/portfolio/household-back.md`, 이력서 블록은 `carrer/resume/household-이력서-블록.md`, 구현 로드맵은 이 레포 `docs/portfolio-sre-roadmap.md`. (직전 트랙: codewalk 시리즈 9개 문서 완결 — 2026-07-03 종료.)

## Status

**로드맵 2번 완결 (2026-07-30) — 자동 복구 리허설.** `infra/backup/restore-drill.sh`(PR #18 머지) 매일 04:00 cron, 최신 R2 백업 → 임시 DB 복구 → 6항목 검증 → drop. 운영 호스트 **RTO=3s** 실측(거래 203건, 덤프 1MB 미만 — 속도 자랑 아니라 기준선 확보/추세 추적 프레임). 주 1회→매일 변경, 체크섬 미채택. **UTF8 인코딩 손상 검사가 핵심** (한글 `?` 치환인데 복구는 "성공"으로 보이는 실패를 로컬 드릴서 겪음) + **신선도 26h assert** (백업 멈춰도 옛 덤프는 복구되니 매일 OK 찍히는 구멍). 포폴 카드 4 + 이력서 블록 + 로드맵 반영 완료. 남은 흠 = 실패 알림 없음(로그만) → 로드맵 3번에서 닫힘.

**(이전) 로드맵 1번 전체 완결 (2026-07-28) — 테스트 49 passed(멱등성 14+3 / 스케줄러 8 / smoke 3 / 도메인 21, 멱등성 97% · 락 로직 100%) + CI 게이트(test.yml reusable 을 ci.yml·deploy.yml 이 공유, 백업 게이트와 2중). 2026-07-30 포폴 카드 4장 확정: 멱등성 / 테스트+CI / 배포 안전망 / 복구되는 백업 (+보조 2: advisory lock·AI 추적). 백필 카드는 도메인 설명 비용으로 제거 — 면접 재료로만 보존. 다음 = 로드맵 2번(주간 복구 리허설 + RTO 실측).**

**D 종합 (도메인 21 케이스)**: D1 원장 running balance 5(GREEN) / D1-6 깨진 커서 3(⚪ 의도된 한계) / **D2 실현손익 4(RED 2 → 소스 결함 1건 수정)** / D3 가계부 격리 5(GREEN) / D4 수량·상태 전이 4(GREEN). **D2 만 갈린 이유** — D1·D2 는 똑같이 "값을 두 곳에서 계산"하는 구조인데 D1 은 두 경로의 순서·규칙이 일치했고 D2 는 입력 순서 vs `tx_date asc` 로 갈렸다. 구조가 아니라 **두 경로가 같은 순서·같은 규칙을 보는가**가 결함을 가른다(면접 카드). **D4-2 가 D2 수정의 개선을 박제** — 수정 전엔 전량매도 시 `quantity` 가 마지막 보유량으로 남았고(운영 DB 점검서 25·101·115주 화석 확인), 이제 replay 가 0 까지 맞춘다. **D1-6c 면접 미끼**: 커서에 carry 를 실으면 클라이언트가 잔액 기준점을 통제 — 숫자로 파싱만 되면 서버가 검증 없이 쓴다. read-only 라 피해는 자기 화면뿐이고, 고치려면 매 페이지 재계산(성능) 또는 커서 HMAC 이라 이 규모엔 과함(C 와 같은 "수정 비용이 방어 논리를 가른다").

**D1 계좌 원장 running balance (`tests/domain/test_account_ledger.py`, 5 케이스 전부 GREEN, 소스 결함 0)**: 불변식 5개를 docstring 에서 도출 — A 닫힘(끝까지 순회 시 마지막 행 `balance_after − signed_amount == start_balance`) / B 페이지 불변(`limit=100` 1페이지 == `limit=2` 3페이지) / C 월 기준점(다음 달 거래 추가해도 당월 잔액 불변) / D 이체 부호(출금 −, 입금 +) / E 평가조정 부호(INCREASE +, DECREASE −). **착수 전 코드 독해로 GREEN 을 예측했고 그대로 나왔다** — D2 와 같은 "값을 두 곳에서 계산" 구조지만 `_signed_amount`(service.py:422) 와 `sum_for_account`(repository.py:185) 의 부호 규칙이 일치하고, 조회/합산 필터도 `or_(account_id, to_account_id)` 로 대칭이라 안 갈렸다. **결함을 가른 건 구조가 아니라 두 경로가 같은 순서·같은 규칙을 보는가** — D2 는 입력순서 vs `tx_date asc` 로 갈렸다(면접 대비 대비 카드). D1-2 에 **페이지 수 단언**(`paged_pages == 3`)을 넣어 커서가 한 페이지만 돌고도 통과하는 구멍을 막음. 계획: `~/.claude/plans/d1-snug-newt.md`. 미착수 엣지: D1-6 깨진 커서 fallback(`service.py:447,450-451`).

**D2 포트폴리오 실현손익 (`tests/domain/test_portfolio_pnl.py`, 4 케이스)**: 도출 불변식 = "활성 거래 집합이 같으면 realized_pnl·quantity·avg_price 는 재계산 트리거 시점과 무관하게 같다". D2-1(매도 후 재매수 평단)·D2-2(과거 BUY 수정 → SELL 재박제) GREEN, **D2-3·D2-4 RED**. 결함 = **진실 원천 2개** — `buy()`/`sell()` 은 incremental(입력 순서, 그 순간 `item.avg_price`)인데 `_recompute_realized_pnl()` 은 replay(`tx_date asc`, `repository.py:236`). 백데이팅 매수(매도보다 앞선 날짜를 뒤늦게 입력) 시 갈리고, **금액과 무관한 memo 수정 한 번**이 저장값을 뒤집었다(실현손익 25,000 → 0 / 평단 1,666.67 → 1,500). **수정**: buy/sell incremental 제거 → `_recalc_item_from_transactions`(replay) 통일, sell 사전 `realized_pnl` 박제 제거, 전량매도 판정을 replay 결과(`item.quantity == 0`) 기준으로. C 와 달리 **자백 아닌 수정** — 고치는 비용이 한 줄이라 "알고도 안 고쳤다"가 성립 안 함. **D3(IDOR) 강등**: 착수 전 `app/domain/*/service.py` public 함수 전수 스캔 → `find_by_id` 후 소속 검증 누락 0건(user 도메인만 예외 = 멤버 초대용 설계 선택, 라우터에 "인증 가드용" 주석 명시). C 핵심 실측: 라우터 성공 후 미들웨어 예외는 **거래 1건이 남는다**(A9 은 0건) → `call_next` 반환 시점에 `get_db` 커밋이 이미 끝났다는 직접 증거 = crash window 실재. C3 는 TTL 만료 후 재시도 시 **거래 2건** → exactly-once 아님 확정. codex 반영: 용어를 fault injection(C1)/state-based simulation(C2·C3)으로 분리, 다른 crash 지점 4개는 최종 상태가 C1·C2 로 수렴함을 논증해 기각, 면접 반격 4개는 `SCENARIOS.md` 표로 보관. B 는 codex 교차검증 3건 중 2건 채택 — `pg_backend_pid()` 상이 단언(독립 커넥션 자립 증명) + **B6 동시 `run_locked_job` 경합**(계약 "다중 워커 동시 진입 시 1개만" 직접 검증, `asyncio.Event` 로 순서 고정해 flaky 제거). nc 용어 정정: A11-nc(보호 제거 → N건)만 역증명, B 의 nc 2개는 상수 오작동 배제 **대조군**. 테스트 0개 → **명세 기반 사후검증**(소스 이미 있음, TDD 신규작성 아님). 계획: `~/.claude/plans/drifting-knitting-corbato.md`. 확정 결정: 실 PG(docker-compose.test) / 스키마 소스 **`Base.metadata.create_all`**(계획의 `alembic upgrade head` 는 이 레포 baseline 이 빈 마이그레이션이라 스키마 0개 생성 → 정정. decisions.md 참조) / 매 테스트 **TRUNCATE**(동시성 때문에 tx-rollback 불가) / **negative control 역증명**(결과 1건만으론 순차와 구분불가 → 락 우회 버전이 N건 만드는 걸 동일 하니스로 대조) / CI **ci.yml+deploy 게이트 둘 다** / 도메인 통합 D는 **🔴 4~5개만**. codex 순서 교차검증 시도 → 이 환경서 긴 프롬프트 hang("OK" 11초는 되나 4질문 분석은 5분+ timeout, 3회) → **자체 ultrathink 로 4질문 대체 검증**: 순서 타당하나 ⓪smoke·⑤CI 명시 추가, ASGITransport 동시성은 진짜 경합 성립(진짜 PG+독립세션+gather)이나 negative control 없으면 극장.

**핵심 제약**: 멱등성 미들웨어가 `async_session()` 직접 사용(DI 아님) → dependency_overrides 로 못 바꿈 → conftest 최상단서 `os.environ` 테스트 PG 주입 **후** 앱 import (config/database 가 import 시점 engine 생성). 멱등성 실증 엔드포인트 = `POST /transaction/create`(user→household→membership→account→category factory 필요).

**(이전 마일스톤) 로드맵·포폴 초안 (2026-07-21) + 노션 재료 (2026-07-22).** 포폴 6카드, 검증 숫자: 도메인 17 / 마이그레이션 22 / 태그 배포 18회 / 잡 5개 / AI 로그 183건. realized_pnl 백필 회고 반영(codex 3차 통과). "운영 성과" ❌ → "운영 준비도·체계" ✅ 톤. nginx 502 건 제외(미적용 상태).

## Context

- **로드맵 순서**: 1 테스트+CI 게이트(실 PostgreSQL 필수, 멱등성 asyncio.gather 동시 N발 + advisory lock 경쟁 + 선택 fault-injection) → 2 주간 자동 복구 리허설(RTO 실측) → 3 장애 알림(잡/백업/배포/헬스체크 webhook) → 4 migration playbook(expand-contract) → 실증: compose 앱 2개 다중 인스턴스 멱등성. 옵션: 용량 한계 실측·오버헤드·무중단 배포. 상세·확정 판단 표는 `docs/portfolio-sre-roadmap.md`.
- **핵심 제약 (재논의 X)**: k6 절대 처리량 폐기 / 멀티스레드 클라이언트 무의미(단일 이벤트 루프) / 멱등성 주장은 "동시 in-flight 중복 방지"까지 — crash window(비즈니스 커밋 후 COMPLETED 전 죽음)는 포폴에 안 쓰고 면접 미끼 / "exactly-once·무장애" 표현 금지.
- 브랜치: `docs/portfolio-sre-roadmap`.

## Next Step

1. ~~**로드맵 1번 전체**~~ **완료** — 테스트 49(⓪ smoke / A 멱등성 14 / B advisory lock 8 / C fault-injection 3 / D 도메인 21) + CI 게이트(ci.yml·deploy.yml → test.yml reusable 공유) + 포폴 실측값 반영. 상세 이력은 Status 참조.
2. ~~**포폴 카드 확정**~~ **완료** (2026-07-30) — 4장 + 보조 2장, 백필 제거. 정본 `carrer/portfolio/household-back.md`, 이력서 블록 `carrer/resume/household-이력서-블록.md`.
3. ~~**로드맵 2번 — 자동 복구 리허설**~~ **완료** (2026-07-30) — 매일 04:00, RTO=3s. 상세는 Status 참조.
4. **다음: 로드맵 3번 — 장애 알림** (Discord/Telegram webhook). 묶을 이벤트: 5xx / 스케줄 잡 실패 / 백업 실패 / 배포 실패 / 헬스체크 / **복구 리허설 실패**(2번이 남긴 빈칸 — 지금은 로그에만 쌓여 리허설이 멈춰도 모름). 이후 4번 migration playbook → 다중 인스턴스 실증.
5. carrer 쪽 남은 것: 면접 대본(포폴 미끼 답변 — crash window / guard 한계 / "백업 수동 개입 0회를 어떻게 확인했나" / **리허설 실패 알림 없음** / **RTO 3초의 근거가 작은 데이터**) + JD 생기면 AI 셀프리뷰 3프롬프트. "복구 리허설 1회" 미끼는 2번으로 닫힘.

**노션 누적 정리 규칙**: 트랙별 하위 페이지에 `## NN.` 섹션 이어붙임 (다시 지시 없어도). 규칙 상세는 harness 메모리 `phase1-notion-worklog`.
- 트랙 1 → "Phase 1 · 테스트 + CI 게이트 — 진행 기록" (https://app.notion.com/p/3a7a6161032981bd8f8bf4f4196584ac)
- 트랙 2 → "Phase 2 · 자동 복구 리허설 — 진행 기록" (2026-07-30 개설)
- 부모 "운영 준비도 로드맵" (https://app.notion.com/p/3a7a6161032980729907d63a113b83cb) 의 `## 1. 작업 목록` 상태·`## 4. 진행 기록` 표도 같이 갱신할 것 — 트랙 1 이 완료됐는데도 ⬜ 로 방치돼 있던 전례 있음.
