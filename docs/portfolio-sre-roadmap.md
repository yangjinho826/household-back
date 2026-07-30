# 포폴 SRE 로드맵 — 운영 강점 카드 실측 보강

> 목적: 이 프로젝트를 이직 포폴 "운영 감각" 카드로 쓰기 위해, 설계 보장형 주장("중복 0건 보장")을 **재현 테스트·실측 기준**으로 격상한다.
> 포폴 본문: `carrer/portfolio/household-back.md` (X 자리를 여기 산출물로 채움).
> 근거: codex 2회 교차검증 (2026-07-21). 포지션 = "저비용 단일 서버를 운영 가능한 상태로 만드는 운영 감각" — 트래픽 카드 아님.

## 로드맵

| 순위 | 작업 | 산출물 (포폴에 채울 것) | 상태 |
|---|---|---|---|
| 1 | **테스트 + CI 게이트** | 통합 테스트 49개(멱등성 14+3 / 스케줄러 8 / smoke 3 / 도메인 21) 실 PostgreSQL — 동일 키 동시 2·10발 → 최종 1건 + A11-nc 대조. ci.yml(PR)·deploy.yml(태그)이 test.yml(reusable) 공유 → 테스트+백업 2중 게이트. 포폴 반영 완료 | ✅ 2026-07-27 |
| 2 | **자동 복구 리허설** | 매일 04:00 최신 백업을 임시 DB 복구·6항목 검증 후 정리. 운영 호스트(1vCPU) **RTO 3초 실측**. 포폴 반영 완료 | ✅ 2026-07-30 |
| 3 | **장애 알림** | "장애 인지: 로그 수동 확인 → 실시간 푸시" | ⬜ |
| 4 | **migration/rollback playbook** | expand-contract 원칙 문서 (면접 방어) | ⬜ |
| 실증 | **다중 인스턴스 멱등성 실증 1회** | "앱 인스턴스 2개가 동일 PostgreSQL 공유 환경에서 동일 키 경합 시 중복 생성 0건" | ⬜ |
| 옵션 | 용량 한계 실측 / 멱등성 오버헤드 실측 / 무중단 배포 | "1vCPU 기준 p95/5xx 꺾이는 지점 → 운영 기준선 산정" | ⬜ |

## 1. 테스트 + CI 게이트 — ✅ 완료 (2026-07-27)

- **실 PostgreSQL 필수** — SQLite/mock 으로 advisory lock·idempotency 동시성 테스트는 무효 (codex: "장난감 테스트"). 로컬(tmpfs 컨테이너)·CI(service 컨테이너) 모두 같은 이미지·포트로 구성 완료.
- 구현된 테스트 (49개, `tests/SCENARIOS.md` 가 정본):
  - A 멱등성 14 + C fault-injection 3: 동시 2·10발 → 최종 1건, A11-nc(보호 제거 → N건) 역증명 포함. crash window(C1)·TTL 재시도 2건(C3) 실측 — 면접 미끼 재료.
  - B advisory lock 8: `pg_backend_pid()` 상이 단언 + B6 동시 `run_locked_job` 경합.
  - D 도메인 21: D1 원장 / D2 실현손익(소스 결함 1건 수정) / D3 격리 / D4 수량·전이.
- CI 게이트: `test.yml`(reusable) 하나를 `ci.yml`(push/PR)과 `deploy.yml`(태그, needs:test)이 공유 — 게이트 드리프트 구조적 차단 + 백업 게이트와 2중.

## 2. 자동 복구 리허설 — ✅ 완료 (2026-07-30)

- **주 1회 → 매일 04:00 로 변경** (백업 03:00 직후). 발견 지연이 7일 → 1일로 줄고 기록도 30배 빨리 쌓인다. `DROP DATABASE` 가 파일을 실제로 지우니 매일 돌려도 볼륨 bloat 없음.
- `infra/backup/restore-drill.sh`: 최신 daily 백업 → 임시 DB restore → 검증 → drop. 소요 시간 = **RTO 실측값**.
- 검증 항목: 백업 신선도(26시간) / gzip 종료코드 / `psql ON_ERROR_STOP` / 테이블 10개 이상 / `users` 행 존재 / **`users.name` 한글 행 존재(UTF8 손상 탐지)**. 체크섬은 채택 안 함 — 덤프는 매일 내용이 달라 고정 기대값이 없고, 위 항목이 "복구 가능"을 더 직접 증명.
- 운영 DB 는 건드리지 않는다. `infra/backup/README.md` 복구 절차의 1~3단계(받기→임시 DB→검증)만 자동화하고, 운영 DB 를 갈아끼우는 swap 단계는 제외.
- **알림은 3번에 의존** — 지금은 `/var/log/household-restore-drill.log` 에만 쌓이고 실패해도 조용하다. 이게 3번의 이벤트 목록에 "복구 리허설 실패"가 들어있는 이유.
- **실측 (2026-07-30 21:48, 운영 호스트)**: `drill OK: household-2026-07-30_030001.sql.gz (0MB) — tables=17 users=4 transactions=203 hangul_ok latest_tx=2026-07-28 RTO=3s`. cron 2줄 등록 확인.
- **RTO 3초 해석 주의** — 거래 203건·덤프 1MB 미만이라 나온 값. 속도 자랑이 아니라 **기준선 확보 + 매일 추세 추적**이 의미. 포폴/이력서도 그 프레임으로 서술.
- 남은 흠: 실패 알림 없음(로그만) → 3번에서 닫힘. `(0MB)` 표기와 cron 로그 노이즈(NOTICE·docker cp 2줄)는 미수정.

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
| 숫자 | 마이그레이션 **24** · 도메인 **17** · 태그 배포 **19** · 통합 테스트 **49** · 잡 5개 · AI 로그 183건 (2026-07-30 재검증) | 전부 git/코드 검증값 — 제출 직전 재검증 커맨드는 포폴 작성 노트 참조 |
| 백필 사고 카드 | 포폴에서 제거 — 면접 재료로만 보존 | 투자 도메인(평단·replay) 설명 비용이 기술 가치를 가림 (2026-07-30, 사용자 판단) |
| 메인 카드 구성 | 배포·멱등성·백업·알림관측 → **멱등성·테스트+CI·배포·백업** (2026-07-30 확정) | 알림관측은 미구현이라 제외 — 로드맵 3번 구현 후 재추가. 정본: `carrer/portfolio/household-back.md` |
