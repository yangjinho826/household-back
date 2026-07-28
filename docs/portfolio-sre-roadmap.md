# 포폴 SRE 로드맵 — 운영 강점 카드 실측 보강

> 목적: 이 프로젝트를 이직 포폴 "운영 감각" 카드로 쓰기 위해, 설계 보장형 주장("중복 0건 보장")을 **재현 테스트·실측 기준**으로 격상한다.
> 포폴 본문: `carrer/portfolio/household-back.md` (X 자리를 여기 산출물로 채움).
> 근거: codex 2회 교차검증 (2026-07-21). 포지션 = "저비용 단일 서버를 운영 가능한 상태로 만드는 운영 감각" — 트래픽 카드 아님.

## 로드맵

| 순위 | 작업 | 산출물 (포폴에 채울 것) | 상태 |
|---|---|---|---|
| 1 | **테스트 + CI 게이트** | "테스트+백업 2중 게이트", "동일 키 동시 요청 N건 재현 — 비즈니스 레코드 1건·캐시 응답 재사용 검증" | ⬜ |
| 2 | **주간 자동 복구 리허설** | "복구 검증 주 1회 자동", "RTO X분 실측" | ⬜ |
| 3 | **장애 알림** | "장애 인지: 로그 수동 확인 → 실시간 푸시" | ⬜ |
| 4 | **migration/rollback playbook** | expand-contract 원칙 문서 (면접 방어) | ⬜ |
| 실증 | **다중 인스턴스 멱등성 실증 1회** | "앱 인스턴스 2개가 동일 PostgreSQL 공유 환경에서 동일 키 경합 시 중복 생성 0건" | ⬜ |
| 옵션 | 용량 한계 실측 / 멱등성 오버헤드 실측 / 무중단 배포 | "1vCPU 기준 p95/5xx 꺾이는 지점 → 운영 기준선 산정" | ⬜ |

## 1. 테스트 + CI 게이트

- **실 PostgreSQL 필수** — SQLite/mock 으로 advisory lock·idempotency 동시성 테스트는 무효 (codex: "장난감 테스트"). CI 에 postgres service 붙일 것.
- 테스트 목록:
  - 멱등성 동시 요청: `httpx.AsyncClient + ASGITransport` + `asyncio.gather` 동시 N발 (같은 user/key/body) → 도메인 레코드 1건 + 캐시 응답 재사용 검증. ASGITransport in-process 여도 `ON CONFLICT` INSERT 가 await 지점이라 경합 실제 성립 (codex 확인).
  - advisory lock 경쟁: 세션 2개가 같은 잡 이름으로 `pg_try_advisory_xact_lock` 경쟁 → 1개만 획득.
  - (선택) fault-injection: 비즈니스 커밋 후 `mark_completed` 전 예외 주입 → 재시도 결과 확인. 면접 역공 카드.
  - 기본 통합 테스트 (도메인 핵심 경로) — 테스트 0개 상태가 최대 구멍.
- `deploy.yml` 에 테스트 job 추가 — 실패 시 배포 중단 (백업 게이트와 2중).

## 2. 주간 자동 복구 리허설

- cron (주 1회): 최신 daily 백업 → 임시 DB restore → 테이블 목록·행수·체크섬 검증 → 결과 알림(3번 연동) → 임시 DB drop.
- 소요 시간 기록 → **RTO 실측값**. 실패 시 알림 필수.
- 기존 문서: `infra/backup/README.md` 의 수동 복구 절차를 자동화하는 것.

## 3. 장애 알림

- 묶을 실패 이벤트: 5xx / 스케줄 잡 실패 / 백업 실패 / 배포 실패 / 헬스체크 실패 / 복구 리허설 실패.
- 채널: Discord/Telegram webhook (기존 `~/.claude/hooks/notify-discord.sh` 참고 가능). Uptime Kuma / Healthchecks.io 류 검토.
- 풀 모니터링 스택(Prometheus+Grafana)은 채택 안 함 — 1vCPU/1GB 리소스 대비 과함 + Monew 포폴과 겹침.

## 4. migration/rollback playbook

- 현재 구조의 약점: entrypoint 자동 `alembic upgrade head` + 이미지 롤백 조합 — DDL 동반 사고 시 수동 복구 (rollback.yml 에도 명시).
- expand-contract 마이그레이션 원칙, backward-compatible release, DDL 포함 배포의 롤백 절차를 `docs/` 에 문서화.

## 확정된 판단 (재논의 X)

| 주제 | 결정 | 근거 |
|---|---|---|
| k6 절대 처리량 | 폐기 | 1vCPU 숫자는 자랑이 아니라 환경 설명. Monew 471→869 옆에서 초라 |
| 부하테스트 프레임 | 옵션 — "용량 한계 실측" | "어디서 무너지고 기준선을 어떻게 잡았나"면 가치 있음 (codex) |
| 동시 중복 검증 도구 | k6 ❌ → pytest (정합성 검증) | 성능이 아니라 correctness |
| 멀티스레드 클라이언트 | 채택 안 함 | 서버가 단일 이벤트 루프 async — 클라이언트 스레드는 검증력 증가 없음. 상위 실증은 **인스턴스 2개** |
| 멱등성 주장 범위 | "동시 in-flight 중복 방지"까지만 | 비즈니스 커밋(get_db) 후 COMPLETED 저장 전 crash → 재시도 중복 가능. "exactly-once 보장" 표현 금지 |
| crash window 포폴 표기 | 안 씀 (면접 미끼) | 룰 미끼 전략 — 답은 면접 대본에서 준비 |
| advisory lock | 독립 카드 ❌ → 보조 | Monew Jenkins 대비 규모·난도 낮게 보임. "같은 문제·다른 제약·다른 선택" 프레임만 |
| 무중단 배포 | 후순위 | 복잡도 대비 신뢰성 리스크 (codex ROI 낮음) |
| 숫자 | 마이그레이션 **22개** (23 아님 — `__pycache__` 오카운트), 도메인 17, 태그 배포 18회, 잡 5개, AI 로그 183건 | 전부 git/코드 검증값 |
