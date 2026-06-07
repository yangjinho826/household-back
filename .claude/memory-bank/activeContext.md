# 활성 컨텍스트

> **두 학습 트랙 병행 중.** 현재 포커스 = **[트랙 A] 소스분석/노션**. [트랙 B] 유닛테스트/TDD는 아래 보존(Part 01·02 완료, Part 03 대기). branch: `docs/codebase-study` (소스분석 학습 전용, main에서 분기).

---

# [트랙 A] 소스분석 학습 (2026-06-07 시작)

## Goal

노션 "가계부 백엔드 API 레퍼런스"(개요 + 0~7 도메인 하위페이지)를 **지도**로 household-back 소스를 0→7 순서로 따라가며 전체 구조·흐름 학습. 바이브 코딩으로 짠 코드라 소스 분석이 덜 됐던 걸 메우는 게 목적.

## Status

**노션 재정리 완료.** 코드 직접 분석(7개 에이전트 병렬 도메인 분석 + 공통 인프라는 직접 Read) 기반:
- 기존 노션 페이지(79 엔드포인트 표) → **개요/인덱스로 재작성** (아키텍처 mermaid / 공통규약 / 추천 읽기순서 0~7 / 도메인 인덱스 / 전역 설계관찰)
- **0~7 도메인 하위페이지 8개 생성** — 각 엔드포인트 `router→service→repository` 흐름 + 모델 + "읽을 파일 순서" + "다른 도메인 의존"
- 코드 워크스루(코드인용+WHY+❌✅)는 **채팅으로** 진행하기로 합의(노션과 중복이라 노션엔 미반영). 채팅 묶음 1(BaseEntity / soft delete / ApiResponse / CamelBaseModel)까지 완료.

## Context

- **노션 개요**: https://app.notion.com/p/374a6161032981029d29d7288152fd29 (본문 읽기순서 표에서 0~7 하위로 점프 + 하단 자동 링크). URL 전체는 notes.md.
- **레이어**: router → service → repository → model, schema=DTO. **공통**: ApiResponse+camelCase(CamelBaseModel), 인증 CurrentUser / 스코프 CurrentHousehold(X-Household-Id), soft delete `data_stat_cd` 50/99, BaseEntity(UUID PK+감사필드), CursorPage(커서 `{정렬키}|{id}`, limit+1), 멱등성(POST+Idempotency-Key), 금액 Money/Quantity, 스케줄러 5잡+advisory lock. **모든 가격 KRW 박제**(USD는 조회/갱신 시 환율 곱함). **ORM relationship 안 씀**(find_by_ids batch).
- **발견한 잠재 버그 2개** → notes.md. 기록만, 수정은 별도 결정.
- 노션은 git 밖(외부)이라 이 트랙의 git 산출물 = 메모리뱅크 기록뿐.

## Next Step

1. 노션 0→7 순서로 소스 따라가기. 다음 = **묶음 2 (인증: jwt.py → deps.py CurrentUser → household/deps.py CurrentHousehold)**. 이후 묶음 3(에러+커서), 묶음 4(멱등성+스케줄러+부팅).
2. 막히는 함수/로직은 채팅으로 ("X가 왜 이렇게 짰어?") → 코드 열어 같이 분석.
3. (선택) 잠재 버그 2개 수정 여부 결정 (decision-helper or 바로 fix).

---

# [트랙 B] 유닛테스트/TDD 학습 (기존, 보존)

## Goal

**유닛테스트 & TDD 학습 트랙** (2026-06-07 시작). 노션 "유닛테스트와 TDD" 정리(Spring 2강의)를 커리큘럼으로 재구성 → Part별 정리(learning_guide v3) → **household-back `tests/`에 실제 테스트로 적용**. 포폴=FastAPI, 실무=Spring을 개념 축으로 병행. SRE 로드맵 Phase 0의 tests/ 셋업과 직접 연결.

## Status

**커리큘럼 작성 완료. Part 01·02 작성 완료(카페키오스크 예시로 재작성), Part 03부터 대기.** → `docs/testing/00-curriculum.md` (5섹션 12 Part).

- 각 Part = `개념(언어무관) → Spring 구현(노션) → FastAPI 매핑(household 적용)` 3단
- 풀 보충 채택: 🆕테스트 피라미드(01)·pytest-asyncio(05)·Testcontainers(09)·FastAPI 스택 httpx+ASGITransport/dependency_overrides(10)·커버리지(12)
- 노션 소스 4노트: 01.TDD소개 / 03.TDD주기 / Spring TDD / Practical Testing(박우빈). **JS 강의·Django·빈 체크리스트 제외**

## Context

- **학습 방식 = A모드(학습 우선)**: 개념/트레이드오프를 결정 근거로 남기며 진행. 목적 "이력서 어필 = 실무에서 무조건 할 수 있어야" → 면접 꼬리질문 방어가 기준. (decisions.md 2026-06-07 4건 참조)
- **두 강의 스타일 차이**: 강의A(01·03)=통합테스트 우선(TestRestTemplate/RANDOM_PORT)+인터페이스 설계 이론 / 강의B(Practical)=단위→통합 피라미드+레이어별(@DataJpaTest/@WebMvcTest)+Mock 깊이+테스트 철학. → 하나로 통합 재구성.
- **tests/ 현 상태 = 백지**: `tests/__pycache__/`만 유물. **소스 .py 없음, git 무이력**. pytest/pytest-asyncio/pytest-mock 의존성은 설치됨, `[tool.pytest.ini_options]`/asyncio_mode **미설정**.
- **Part 작성 규칙 (사용자 피드백 2026-06-07, 확정)**:
  1. 예시 = **카페 키오스크** 도메인. **입문자도 이해 가능하게** 클래스 정의·맥락 먼저.
  2. **모음 실제 코드 완전 제외** — 도메인 지식이 학습 노이즈라 제외. 실제 테스트는 tests/ 짤 때 따로.
  3. 3단 매핑: `개념 → Spring(카페키오스크) → FastAPI(같은 소재 pytest 변환)`.
  4. `(실무)`/`(포폴)` 라벨 없이 **프레임워크명만**.
  5. 제품 지칭은 브랜드명 **"모음"** (코드 경로 household-back은 그대로).

## Next Step (트랙 B)

1. **"Part 03 해줘"** → learning_guide v3 형식 Part 03(구조와 단언) 작성. `docs/testing/03-*.md` (이미 작성됨 — 확인 필요) → Part 06부터일 수 있음, 커리큘럼.md 진행표 확인.
2. Part 진행 시 커리큘럼.md 진행상황 테이블 ⏳→✅ 갱신.

---

## 향후 큰 목표 — SRE 운영 트랙 (포트폴리오 차별화)

이직용 포트폴리오 차별화 — `household-back` + `household-front` 가계부를 **"1인 SRE가 실제로 운영하는 부부 공유 가계부 SaaS"** 컨셉으로 확장.

핵심 한 줄: SLO 정의 → 메트릭/로그/트레이싱/알람 풀스택 관측성 → 인위 장애 시나리오로 인시던트 대응 → RUNBOOK·회고 작성. iOS/Android 스토어 배포 포함.

**3가지 핵심 결정 (확정)**
1. 모니터링: 하이브리드 — Sentry + Prometheus/Grafana + Loki + Tempo + Uptime Kuma + OpenTelemetry
2. 어플 배포: Capacitor wrap (PWA → App Store / Play)
3. 운영 깊이: Level 3 (RUNBOOK + 인위 인시던트 2건 + 회고)

**로드맵 (7 Phase)**: 0.기반(tests+pre-commit+/health) → 1.Sentry → 2.Prom/Grafana/Loki → 3.OTel/Tempo/Uptime → 4.Alertmanager/SLO/Discord → 5.Capacitor → 6.RUNBOOK/인시던트/회고 → 7.README. 추천 순서 0→1→5→2→3→4→6→7. 상세: `~/.claude/plans/hashed-inventing-sprout.md`.

> **현재 테스트 학습 트랙이 Phase 0(tests/ 셋업)을 학습과 함께 채우는 중** — 학습으로 짠 테스트가 곧 Phase 0 산출물. 소스분석 트랙(A)은 그 전제(코드 이해)를 다지는 역할.
