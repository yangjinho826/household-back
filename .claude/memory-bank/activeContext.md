# 활성 컨텍스트

## Goal

**이직 포폴 "운영 강점" 카드화 + SRE 로드맵 실행** (2026-07-21 시작). household-back 을 이력서/포폴에 추가 — 포지션은 "저비용 단일 서버를 운영 가능한 상태로 만드는 운영 감각" 보조 카드 (트래픽 카드 아님, codex 2회 교차검증). 포폴 본문은 `carrer/portfolio/household-back.md`, 이력서 블록은 `carrer/resume/household-이력서-블록.md`, 구현 로드맵은 이 레포 `docs/portfolio-sre-roadmap.md`. (직전 트랙: codewalk 시리즈 9개 문서 완결 — 2026-07-03 종료.)

## Status

**로드맵 1번 ① 시나리오 + A 멱등성 완결 (2026-07-27) — `tests/idempotency/` 14 케이스 통과, 멱등성 코어 커버리지 92%, 소스 결함 0. 다음 B advisory lock.** 테스트 0개 → **명세 기반 사후검증**(소스 이미 있음, TDD 신규작성 아님). 계획: `~/.claude/plans/drifting-knitting-corbato.md`. 확정 결정: 실 PG(docker-compose.test) / 스키마 소스 **`Base.metadata.create_all`**(계획의 `alembic upgrade head` 는 이 레포 baseline 이 빈 마이그레이션이라 스키마 0개 생성 → 정정. decisions.md 참조) / 매 테스트 **TRUNCATE**(동시성 때문에 tx-rollback 불가) / **negative control 역증명**(결과 1건만으론 순차와 구분불가 → 락 우회 버전이 N건 만드는 걸 동일 하니스로 대조) / CI **ci.yml+deploy 게이트 둘 다** / 도메인 통합 D는 **🔴 4~5개만**. codex 순서 교차검증 시도 → 이 환경서 긴 프롬프트 hang("OK" 11초는 되나 4질문 분석은 5분+ timeout, 3회) → **자체 ultrathink 로 4질문 대체 검증**: 순서 타당하나 ⓪smoke·⑤CI 명시 추가, ASGITransport 동시성은 진짜 경합 성립(진짜 PG+독립세션+gather)이나 negative control 없으면 극장.

**핵심 제약**: 멱등성 미들웨어가 `async_session()` 직접 사용(DI 아님) → dependency_overrides 로 못 바꿈 → conftest 최상단서 `os.environ` 테스트 PG 주입 **후** 앱 import (config/database 가 import 시점 engine 생성). 멱등성 실증 엔드포인트 = `POST /transaction/create`(user→household→membership→account→category factory 필요).

**(이전 마일스톤) 로드맵·포폴 초안 (2026-07-21) + 노션 재료 (2026-07-22).** 포폴 6카드, 검증 숫자: 도메인 17 / 마이그레이션 22 / 태그 배포 18회 / 잡 5개 / AI 로그 183건. realized_pnl 백필 회고 반영(codex 3차 통과). "운영 성과" ❌ → "운영 준비도·체계" ✅ 톤. nginx 502 건 제외(미적용 상태).

## Context

- **로드맵 순서**: 1 테스트+CI 게이트(실 PostgreSQL 필수, 멱등성 asyncio.gather 동시 N발 + advisory lock 경쟁 + 선택 fault-injection) → 2 주간 자동 복구 리허설(RTO 실측) → 3 장애 알림(잡/백업/배포/헬스체크 webhook) → 4 migration playbook(expand-contract) → 실증: compose 앱 2개 다중 인스턴스 멱등성. 옵션: 용량 한계 실측·오버헤드·무중단 배포. 상세·확정 판단 표는 `docs/portfolio-sre-roadmap.md`.
- **핵심 제약 (재논의 X)**: k6 절대 처리량 폐기 / 멀티스레드 클라이언트 무의미(단일 이벤트 루프) / 멱등성 주장은 "동시 in-flight 중복 방지"까지 — crash window(비즈니스 커밋 후 COMPLETED 전 죽음)는 포폴에 안 쓰고 면접 미끼 / "exactly-once·무장애" 표현 금지.
- 현재 테스트 0개 (main에도 없음) — 이게 최대 구멍이라 1순위.
- 브랜치: `docs/portfolio-sre-roadmap`.

## Next Step

1. ~~**⓪ 환경**~~ **완료**(smoke 3/3). ~~**① SCENARIOS.md + factory.py + A 멱등성**~~ **완료**(14 케이스, A1~A12 + A11/A11-nc 대조, 커버리지 92%). codex 교차검증 반영(A11-nc 재설계·A12 4xx 캐싱). 소스 결함 0, 면접 미끼 2개(A10 경로 실체·4xx 캐싱).
2. **다음: B advisory lock**(`tests/scheduler/` — B1 세션2개 같은 job 1개만 / B2 다른 job 둘 다 / B3 xact 후 재획득 / B4 실패 skip / B5 예외 롤백) → **C fault-injection**(crash window 면접 미끼) → **D 도메인 🔴 4~5개**.
3. **④ RED 분석·수정** → **⑤ CI**(ci.yml + deploy 게이트) → **⑥ 포폴 X 채움**(A11/A11-nc 대조 결과 = "동일 키 동시 N건 → 1건" 실측 확정).
4. 이후 로드맵 2→3→4→실증. 완성 후: JD + AI 셀프리뷰 3프롬프트 + 면접 대본 — `carrer/interview/`.

**노션 누적 정리 규칙**: phase1 각 단계 완료 시 다시 지시 없어도 노션 "Phase 1 진행기록"(https://app.notion.com/p/3a7a6161032981bd8f8bf4f4196584ac) 에 `## NN.` 섹션 이어붙임. 규칙 상세는 harness 메모리 `phase1-notion-worklog`.
