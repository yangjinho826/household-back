# 활성 컨텍스트

> **이 브랜치(`docs/codebase-study`)는 소스분석 전용.** main에서 분기. 노션을 지도로 household-back 소스를 0→7 순서로 따라가며 구조·흐름 학습.

---

# 소스분석 학습 (2026-06-07 시작)

## Goal

노션 "가계부 백엔드 API 레퍼런스"(개요 + 0~7 도메인 하위페이지)를 **지도**로 household-back 소스를 0→7 순서로 따라가며 전체 구조·흐름 학습. 바이브 코딩으로 짠 코드라 소스 분석이 덜 됐던 걸 메우는 게 목적.

## Status

**노션 재정리 완료.** 코드 직접 분석(7개 에이전트 병렬 도메인 분석 + 공통 인프라는 직접 Read) 기반:
- 기존 노션 페이지(79 엔드포인트 표) → **개요/인덱스로 재작성** (아키텍처 mermaid / 공통규약 / 추천 읽기순서 0~7 / 도메인 인덱스 / 전역 설계관찰)
- **0~7 도메인 하위페이지 8개 생성** — 각 엔드포인트 `router→service→repository` 흐름 + 모델 + "읽을 파일 순서" + "다른 도메인 의존"
- 코드 워크스루(코드인용+WHY+❌✅)는 **채팅으로** 진행하기로 합의(노션과 중복이라 노션엔 미반영).
- **워크스루 0부터 다시 시작하기로 결정 (이전 진행분 리셋).** 워크스루 번호 = 노션 도메인 번호(0~7)에 맞춤. → 0.공통인프라(core) / 1.auth·user / 2.household / 3.account·category / 4.transaction / 5.fixed·snapshot / 6.portfolio·market·exchange / 7.stats·home·wealth·settings·enum·health. (예전 "묶음1=BaseEntity~" 체계는 폐기)
- **아직 워크스루 미시작** — 다음 세션에 0번부터.

## Context

- **노션 개요**: https://app.notion.com/p/374a6161032981029d29d7288152fd29 (본문 읽기순서 표에서 0~7 하위로 점프 + 하단 자동 링크). URL 전체는 notes.md.
- **레이어**: router → service → repository → model, schema=DTO. **공통**: ApiResponse+camelCase(CamelBaseModel), 인증 CurrentUser / 스코프 CurrentHousehold(X-Household-Id), soft delete `data_stat_cd` 50/99, BaseEntity(UUID PK+감사필드), CursorPage(커서 `{정렬키}|{id}`, limit+1), 멱등성(POST+Idempotency-Key), 금액 Money/Quantity, 스케줄러 5잡+advisory lock. **모든 가격 KRW 박제**(USD는 조회/갱신 시 환율 곱함). **ORM relationship 안 씀**(find_by_ids batch).
- **발견한 잠재 버그 2개** → notes.md. 기록만, 수정은 별도 결정.
- 노션은 git 밖(외부)이라 이 트랙의 git 산출물 = 메모리뱅크 기록뿐.

## 소스 전체 흐름 (한 장 요약 — 내일 따라갈 지도)

> "이 플젝이 전체적으로 어떤 흐름이냐" 에 대한 답. 내일 0번부터 코드로 검증.

**스택**: FastAPI + SQLAlchemy 2.x(async) + PostgreSQL + APScheduler. `app/main.py`가 `root_path="/api"` (모든 경로 `/api` 하위). 도메인형 레이어드 — 도메인마다 `router/service/repository/model/schema(+enum)` 동일 5~6파일.

**요청 1건이 거치는 길** (front → DB → front):

| 단계 | 무슨 일 | 파일 |
|---|---|---|
| 1. 미들웨어 | POST+`Idempotency-Key`면 멱등 처리. 모든 요청 access log 1줄 | `core/idempotency/middleware.py`, `core/middleware/access_log.py` |
| 2. 라우터+의존성 | `Depends`로 `CurrentUser`(JWT) / `CurrentHousehold`(X-Household-Id+멤버십) / `get_db` 주입 | `core/auth/deps.py`, `domain/household/deps.py`, `core/database.py` |
| 3. 서비스 | 검증→비즈니스 로직. **여기가 트랜잭션 경계**(get_db 정상종료 commit, 예외 rollback) | `domain/*/service.py` |
| 4. 리포지토리 | `select()` 쿼리만. 조인 대신 `find_by_ids` batch(N+1 회피) | `domain/*/repository.py` |
| 5. 응답 | 도메인→`*Response`→`ApiResponse.ok()`. snake→camel 자동 | `core/api_response.py`, `core/schema.py` |
| 예외 | `CustomException(ErrorCode)`→핸들러가 전부 ApiResponse JSON(한국어) | `core/exceptions/handlers.py` |

**읽기 순서 0→7** (의존성 위→아래, 위가 아래 전제):
`0.core`(전제) → `1.auth·user`(인증 출발) → `2.household`(스코프·멤버) → `3.account·category`(거래 재료) → `4.transaction`(★핵심, 5타입+달력+원장) → `5.fixed·snapshot`(고정지출+자산박제) → `6.portfolio·market·exchange`(★최난도, 평단·시세·환율) → `7.stats·home·wealth·settings·enum·health`(집계/합성).

**전역 6패턴** (이거 알면 전 도메인이 같은 방식으로 읽힘): notes.md "학습 노트" 참조 — ①relationship 안 씀(find_by_ids batch) ②soft delete 기본('99')+수동 cascade ③household 스코프 강제(위반=NOT_FOUND 은닉) ④가격 KRW 박제 ⑤커서 페이징 통일 ⑥overview 3종은 합성만.

## Next Step

1. **워크스루 0번(공통 인프라/core)부터 시작** — 노션 0번 페이지를 지도로 core 코드 따라가기. 0번 페이지의 "읽을 파일 순서" 9단계: ①`core/model.py`+`enums/data_status.py`(BaseEntity·soft delete) ②`core/schema.py`+`api_response.py`(응답봉투) ③`core/auth/jwt.py`→`deps.py`→`extract.py`(인증) ④`domain/household/deps.py`(스코프) ⑤`core/exceptions/error_code.py`→`handlers.py`(에러) ⑥`core/pagination.py`(커서) ⑦`core/idempotency/middleware.py`+`service.py`(멱등성) ⑧`core/scheduler.py`+`jobs.py`(스케줄러) ⑨`core/database.py`+`config.py`+`main.py`(부팅). 이후 1→7.
2. 막히는 함수/로직은 채팅으로 ("X가 왜 이렇게 짰어?") → 코드 열어 같이 분석.
3. (선택) 잠재 버그 2개 수정 여부 결정 (decision-helper or 바로 fix).

---

## 향후 큰 목표 — SRE 운영 트랙 (포트폴리오 차별화)

이직용 포트폴리오 차별화 — `household-back` + `household-front` 가계부를 **"1인 SRE가 실제로 운영하는 부부 공유 가계부 SaaS"** 컨셉으로 확장.

핵심 한 줄: SLO 정의 → 메트릭/로그/트레이싱/알람 풀스택 관측성 → 인위 장애 시나리오로 인시던트 대응 → RUNBOOK·회고 작성. iOS/Android 스토어 배포 포함.

**3가지 핵심 결정 (확정)**
1. 모니터링: 하이브리드 — Sentry + Prometheus/Grafana + Loki + Tempo + Uptime Kuma + OpenTelemetry
2. 어플 배포: Capacitor wrap (PWA → App Store / Play)
3. 운영 깊이: Level 3 (RUNBOOK + 인위 인시던트 2건 + 회고)

**로드맵 (7 Phase)**: 0.기반(tests+pre-commit+/health) → 1.Sentry → 2.Prom/Grafana/Loki → 3.OTel/Tempo/Uptime → 4.Alertmanager/SLO/Discord → 5.Capacitor → 6.RUNBOOK/인시던트/회고 → 7.README. 추천 순서 0→1→5→2→3→4→6→7. 상세: `~/.claude/plans/hashed-inventing-sprout.md`.

> **소스분석 트랙은 그 전제(코드 이해)를 다지는 역할.**
