# 활성 컨텍스트

## Goal

**이직 포폴 "운영 강점" 카드화 + SRE 로드맵 실행** (2026-07-21 시작). household-back 을 이력서/포폴에 추가 — 포지션은 "저비용 단일 서버를 운영 가능한 상태로 만드는 운영 감각" 보조 카드 (트래픽 카드 아님, codex 2회 교차검증). 포폴 본문은 `carrer/portfolio/household-back.md`, 이력서 블록은 `carrer/resume/household-이력서-블록.md`, 구현 로드맵은 이 레포 `docs/portfolio-sre-roadmap.md`. (직전 트랙: codewalk 시리즈 9개 문서 완결 — 2026-07-03 종료.)

## Status

**로드맵·포폴 초안 확정 (2026-07-21).** 포폴 6카드 = 메인4(배포 안전망 / POST 멱등성 / 3계층 백업+복구 리허설 / 장애 알림·관측) + 보조2(advisory lock 한 줄 / AI 코드 이력 추적 183건). `(→ N번 후)` 표시 문장(테스트 검증·RTO·알림)은 로드맵 구현 후 X 채워 확정. 검증된 숫자: 도메인 17 / 마이그레이션 **22**(23은 `__pycache__` 오카운트) / 태그 배포 18회 / 잡 5개 / AI 로그 183건. 실운영 상태: 배포됐지만 실사용 미미 → "운영 성과" 아닌 "운영 준비도·체계" 톤 필수.

## Context

- **로드맵 순서**: 1 테스트+CI 게이트(실 PostgreSQL 필수, 멱등성 asyncio.gather 동시 N발 + advisory lock 경쟁 + 선택 fault-injection) → 2 주간 자동 복구 리허설(RTO 실측) → 3 장애 알림(잡/백업/배포/헬스체크 webhook) → 4 migration playbook(expand-contract) → 실증: compose 앱 2개 다중 인스턴스 멱등성. 옵션: 용량 한계 실측·오버헤드·무중단 배포. 상세·확정 판단 표는 `docs/portfolio-sre-roadmap.md`.
- **핵심 제약 (재논의 X)**: k6 절대 처리량 폐기 / 멀티스레드 클라이언트 무의미(단일 이벤트 루프) / 멱등성 주장은 "동시 in-flight 중복 방지"까지 — crash window(비즈니스 커밋 후 COMPLETED 전 죽음)는 포폴에 안 쓰고 면접 미끼 / "exactly-once·무장애" 표현 금지.
- 현재 테스트 0개 (main에도 없음) — 이게 최대 구멍이라 1순위.
- 브랜치: `docs/portfolio-sre-roadmap`.

## Next Step

1. 로드맵 1번: pytest + conftest(실 PG) + 멱등성 동시성 테스트 + CI 테스트 게이트 (`deploy.yml`).
2. 이후 2→3→4 순서로. 각 단계 완료 시 포폴 X 자리 실측값으로 채움.
3. 완성 후: JD 잡고 AI 셀프리뷰 3프롬프트 + 면접 대본(미끼 답변: crash window·advisory lock 한계) — `carrer/interview/`.
