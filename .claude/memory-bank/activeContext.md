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

## Next Step

1. **워크스루 0번(공통 인프라/core)부터 시작** — 노션 0번 페이지를 지도로 core 코드(BaseEntity / soft delete / ApiResponse / CamelBaseModel / 커서 / 멱등성 등) 따라가기. 이후 1→7 순서.
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
