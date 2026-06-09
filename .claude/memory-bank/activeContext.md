# 활성 컨텍스트

> **이 브랜치(`docs/codebase-study`)는 소스분석 전용.** main에서 직접 분기(2026-06-07 git 구조 재정리 완료). 노션을 지도로 household-back 소스를 0→7 순서로 따라가며 구조·흐름 학습.
>
> **브랜치 구조**: `main` ─┬─ `docs/codebase-study`(소스분석 4커밋) └─ `docs/portfolio-sre-roadmap`(SRE+유닛테스트 4커밋). 둘 다 origin 동기화됨.

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
- **워크스루 0번(core) 완주 (2026-06-08)** — 9단계 채팅 워크스루 끝. ①BaseEntity·soft delete ②응답봉투 ③인증 ④스코프 ⑤에러 ⑥페이징 ⑦멱등성 ⑧스케줄러 ⑨부팅. 멱등성을 가장 깊게 팜(process_acquire 상태머신 / INSERT ON CONFLICT DO NOTHING atomic 락 / body sha256 fingerprint / AcquireResult True·False 의미). `idempotency/service.py` AcquireResult 필드에 주석 추가.
- **워크스루 1번(auth·user) 완주 (2026-06-09)** — user(가입/me/search/detail/update) + auth(login/refresh/logout) 흐름. 핵심 ①토큰 2종 비대칭: access=stateless·헤더·DB저장X / refresh=stateful·HttpOnly쿠키·DB저장(폐기가능). ②refresh 회전 최대 5개(`MAX_ACTIVE_TOKENS`, `frst_reg_dt` 오래된 것부터 폐기, `n-5+1`). ③refresh 검증 3단(서명·`type==REFRESH`·DB active). ④`CurrentUser` 2단 의존성 = login 발급 ↔ `get_current_user` 검증 양방향 확인. 곁다리로 관찰점 ①(CustomException이 `ValueError` 아닌 `Exception` 상속 → Pydantic validator 통과 → 구체 에러코드 US003 보존) 추적. **관찰점 2개 notes.md 기록**: get_current_active_user ACTIVE 재확인 dead 분기 / auth service naive `datetime.now`. **다음 세션은 워크스루 2번(household)부터.**
- **(2026-06-07) git 히스토리 재정리 완료** — `docs/codebase-study`가 유닛테스트/SRE 커밋 위에 얹혀 있던 걸 `rebase --onto main`으로 main 바로 위(소스분석 4커밋만)로 분리. 유닛테스트/SRE는 `docs/portfolio-sre-roadmap`에 남김. 내용 손실 0(원본 트리와 diff 비어있음 확인), force push 완료. 원본 안전망 = 로컬 `backup/codebase-study-pre-rebase-5253922`.

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

1. **워크스루 2번(household)부터 시작** — 노션 2번 페이지를 지도로. 스코프·멤버십(`CurrentHousehold`, X-Household-Id) / 멤버 초대(1번 user search 연계) / 소유권 위반=NOT_FOUND 은닉 패턴이 실제 도메인에서 어떻게 쓰이는지 검증. 1번에서 본 `CurrentUser`가 household 스코프와 어떻게 합쳐지는지(2단 deps → 3단?) 확인.
2. 막히는 함수/로직은 채팅으로 ("X가 왜 이렇게 짰어?") → 코드 열어 같이 분석.
3. (보류) 0번서 관찰한 잠재 개선점 2개 — `data_stat_cd` default 없음(생성 시 매번 수동 ACTIVE) / `core/model.py`의 naive `datetime.now`(컬럼은 tz-aware). notes.md 미기록, 수정도 미정.
4. (선택) 기존 잠재 버그 2개 수정 여부 결정 (decision-helper or 바로 fix).
