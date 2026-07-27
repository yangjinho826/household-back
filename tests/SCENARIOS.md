# 테스트 시나리오 체크리스트 (살아있는 목록)

> 명세 기반 사후검증(spec-first characterization). 코드 역도출 X — 공개계약(미들웨어 상태머신 docstring·엔드포인트 계약·모델 제약)에서 시나리오를 독립 도출한 뒤 테스트로 대조한다.
> RED = 코드가 시나리오를 못 지킴 = **실제 버그/누락**(수정 대상). 시나리오가 비현실적이면 시나리오를 보강.
> 위험도: 🔴 돈·정합성 직결 / 🟡 계약 방어 / ⚪ 의도된 한계(면접 미끼).

착수: 2026-07-27 · 브랜치 `docs/portfolio-sre-roadmap` · 계획 `~/.claude/plans/drifting-knitting-corbato.md`

---

## 공개계약 요약 (도출 근거)

**멱등성 미들웨어** (`app/core/idempotency/middleware.py`)
- 게이트 3조건 (미통과 시 그냥 패스): `POST` + `Idempotency-Key` 헤더 + 유효 JWT(`extract_user_id` 성공)
- 상태머신: 새 키 → PENDING INSERT(`ON CONFLICT DO NOTHING` = atomic 락) → 라우터 → 성공 COMPLETED 저장 / 5xx·예외 PENDING 해제(재시도 허용)
- COMPLETED 키 재요청 → 라우터 실행 X, 캐시 응답(status·body·headers 복원)
- 충돌 분기: 같은 키 다른 method·path → `KEY_CONFLICT` / 다른 body → `BODY_MISMATCH` / PENDING 중 재진입 → `IN_PROGRESS`
- 멱등 단위 = `(user_id, key)` unique. body fingerprint = `sha256(raw body)`

**실증 엔드포인트**: `POST /transaction/create` — `CurrentUser`(Bearer `sub`) + `CurrentHousehold`(`X-Household-Id` + 멤버십) 필요.

---

## A. 멱등성 🔴 (`tests/idempotency/`)

| # | 시나리오 | 기대 | 위험 | 상태 |
|---|---|---|---|---|
| A1 | POST 아님(GET) + 키 있음 | 미들웨어 패스 (레코드 0건) | 🟡 | ✅ |
| A2 | POST + 키 없음 | 미들웨어 패스 (레코드 0건), 거래는 생성 | 🟡 | ✅ |
| A3 | POST + 키 + JWT 없음 | 미들웨어 패스 (레코드 0건), 라우터서 401/403 | 🟡 | ✅ |
| A4 | 새 키 1회 | **200**(201 아님 — 라우터에 status_code 미지정) + 거래 1건 + COMPLETED 레코드 1건 | 🔴 | ✅ |
| A5 | 같은 키 2회(순차, COMPLETED) | 2번째는 라우터 재실행 X → 거래 여전히 1건, 응답 바디·status 동일(캐시) | 🔴 | ✅ |
| A6 | 같은 키·다른 path | `KEY_CONFLICT` (422/ID001) | 🟡 | ✅ |
| A7 | 같은 키·다른 body | `BODY_MISMATCH` (422/ID002) | 🔴 | ✅ |
| A8 | PENDING 상태서 같은 키 재진입 | `IN_PROGRESS` (409/ID003) | 🟡 | ✅ |
| A9+A10 | 라우터 예외/5xx | PENDING 해제(레코드 0건) → 재시도 시 성공. **A10 통합**: 글로벌 Exception 핸들러가 미들웨어보다 바깥(ServerErrorMiddleware)이라 call_next 가 예외를 raise 로 받아 `except` 블록(release+re-raise)을 탐 → 최종 500. 별도 A10 아님 | 🔴 | ✅ |
| **A11** | **동시 N발**(`asyncio.gather`, 같은 user/key/body) N=2·N=10 | 거래 정확히 1건 + 레코드 1건. 응답 분포: 1개 200(원본/캐시), 나머지 캐시 or IN_PROGRESS | 🔴 | ✅ |
| **A11-nc** | **negative control**: 멱등성 보호를 끈 채(= `Idempotency-Key` 헤더 없이) 동일 gather N발 | 거래 N건 생성됨 → A11 의 "1건"이 순차 우연이 아닌 진짜 경합 차단 결과임을 역증명 | 🔴 | ✅ |
| A12 | 4xx 응답(validation/domain 실패) 후 같은 키·같은 body 재요청 | 미들웨어가 4xx 도 COMPLETED 캐시(`>=500` 만 해제) → 라우터 재실행 X, 캐시된 4xx 반환. **계약 확인됨** | 🟡 | ✅ |

> A11-nc 없으면 A11 의 "1건"은 순차 실행과 구분 불가(올바른 멱등성은 순차도 1건). 보호 없는 동일 하니스가 N건 만드는 걸 보여야 경합이 실재함이 증명된다.
> **주의(codex 검증)**: `ON CONFLICT DO NOTHING` 만 제거하는 mutant 는 `uq_idempotency_user_key` unique 제약 때문에 IntegrityError/500 이 나 negative control 로 부적합 → **보호 자체를 끄는(키 헤더 제거)** 방식으로 N건을 관찰한다. `ON CONFLICT` 락 자체를 특정 검증하려면 unique 제약까지 제거한 mutant 가 필요(선택, 복잡도 높아 보류).
> **A12 근거(codex 검증)**: `middleware.py` 는 `status_code >= 500` 에서만 release → 4xx 는 COMPLETED 로 캐시된다. "4xx 를 멱등 캐시하는 게 맞나"는 논쟁적(재시도로 고칠 수 있는 검증 실패까지 굳힘) — 면접 방어 포인트로 보관.

## B. advisory lock 🟡 (`tests/scheduler/`)
| # | 시나리오 | 상태 |
|---|---|---|
| B1 | 세션 2개 같은 job key → 1개만 획득(True) | ⬜ |
| B2 | 다른 job key → 둘 다 획득 | ⬜ |
| B3 | xact 종료 후 재획득 가능 | ⬜ |
| B4 | lock 실패 시 fn skip | ⬜ |
| B5 | fn 예외 → 롤백 + 재발생 | ⬜ |

## C. fault-injection ⚪ (면접 미끼, `tests/idempotency/`)
| # | 시나리오 | 상태 |
|---|---|---|
| C1 | 비즈 커밋 후 `mark_completed` 전 예외 주입 → release → 재시도서 **재실행**(crash window = exactly-once 아님을 자백). 소스 안 고침 | ⬜ |

## D. 도메인 핵심 🔴 4~5개 (`tests/domain/`)
| # | 시나리오 | 상태 |
|---|---|---|
| D1 | transaction create → 계좌 ledger running balance 정합 | ⬜ |
| D2 | portfolio realized_pnl (백필 사고 로직) | ⬜ |
| D3 | household IDOR — 타 household 리소스 접근 차단 | ⬜ |
| D4 | auth 로그인·토큰 발급/검증 | ⬜ |

> D 최종 대상은 A~C 끝난 뒤 각 도메인 공개계약 읽고 확정.
