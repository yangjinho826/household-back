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

**공개계약** (`app/core/scheduler.py` docstring)
- `try_advisory_lock(session, key) -> bool` — `pg_try_advisory_xact_lock(hashtext(key))`. **트랜잭션 스코프**(tx 종료 시 자동 해제, 명시 unlock 없음) / 실패 시 **대기 없이 False**(호출자가 skip 결정) / "같은 잡이 다중 인스턴스·워커에서 동시 진입해도 1개만 통과"
- `run_locked_job(job_name, fn)` — ① 자체 `async_session`(요청 DI 와 분리) ② 명시 `session.begin()`(락 유효 범위 = 이 tx) ③ 락 실패 시 **조용히 skip**(fn 미호출·예외 X·info 로그) ④ `fn(session)` 실행 ⑤ 예외는 로그 후 **재발생**(begin 컨텍스트 이탈 → 롤백)

| # | 시나리오 | 기대 | 위험 | 상태 |
|---|---|---|---|---|
| B1 | 세션 2개(독립 커넥션)가 tx 를 연 채 같은 key | 1번째 True / 2번째 **False** — 블로킹 없이 즉시. `pg_backend_pid()` 상이도 함께 단언 | 🟡 | ✅ |
| **B1-nc** | 대조군: **같은 세션**이 같은 key 2회 | 둘 다 True — 판정 단위가 커넥션임을 보이고, B1 의 False 가 "무조건 False" 가 아님을 배제 | 🟡 | ✅ |
| B2 | 세션 2개, **다른** key | 둘 다 True — 락이 잡 이름 단위로 분리 | 🟡 | ✅ |
| B3 | 세션1 tx 종료 후 세션2가 같은 key | True — xact 스코프라 명시 unlock 없이 자동 해제 | 🟡 | ✅ |
| B4 | 외부 세션이 key 선점 → `run_locked_job(같은 이름)` | fn **미호출**(0회) + 예외 없이 정상 반환(skip) | 🟡 | ✅ |
| **B4-nc** | 대조군: 선점 없이 같은 `run_locked_job` | fn **1회 호출** + 쓴 행 커밋됨 — B4 의 미호출이 락 때문임을 배제 검증 | 🟡 | ✅ |
| **B6** | `run_locked_job` 2개 **동시 실행**(`asyncio.gather`, 같은 잡 이름) | fn 총 **1회**만 실행 + 행 1건 — 계약의 "다중 인스턴스·워커 동시 진입 시 1개만 통과" 직접 검증 | 🔴 | ✅ |
| B5 | fn 이 행 INSERT 후 예외 | 예외 **재발생**(호출자로 전파) + INSERT 롤백(0건) | 🔴 | ✅ |

> B1/B4 의 nc 는 "상수 False·상수 미호출" 오작동을 배제하는 **대조군**이지, 락을 제거한 mutant 로 N건을 관찰하는 A11-nc 급 역증명은 아니다(codex 지적 채택). 완전 역증명은 `pg_try_advisory_xact_lock` 자체를 무력화한 변형이 필요 — 복잡도 대비 이득이 낮아 보류.
> **B6 은 codex 교차검증에서 나온 누락**(B4 는 수동 holder 라 "동시 진입"의 간접 증거). `asyncio.Event` 로 순서를 고정해 flaky 를 제거했다 — 경쟁자는 첫 잡이 락을 쥔 동안에만 시도하고, 첫 잡은 경쟁자 판정이 끝난 뒤 진행한다.
> job key 는 테스트마다 uuid — advisory lock 은 **DB 전역 네임스페이스**라 고정 문자열이면 테스트 간 간섭이 난다.

## C. fault-injection ⚪ (면접 미끼, `tests/idempotency/test_crash_window.py`)

> **이 섹션의 RED 는 수정 대상이 아니라 자백 대상이다.** A·B 가 "계약이 지켜짐"을 증명했다면 C 는 안 지켜지는 구간을 통과하는 테스트로 박제한다. 소스는 안 고친다 — "알고도 안 고쳤다"가 면접 카드(`docs/portfolio-sre-roadmap.md` 확정 판단).

**crash window 위치** (`middleware.py:92-109`)
```python
response = await call_next(request)              # 92  라우터 실행 → 비즈 tx COMMIT (database.py:51)
captured_body = await capture_response_body(response)
                                                 # ←── 여기서 죽으면
await idempotency_service.mark_completed(...)    # 101 멱등 레코드는 아직 PENDING
await session.commit()                           # 109
```
- 프로세스가 죽으면 `except` 의 `release`(113)조차 못 돈다 → PENDING 잔류 → 같은 키 재시도는 `IN_PROGRESS`(409)로 차단
- `PENDING_TTL_SECONDS = 60`(`constants.py:2`) 경과 후 `cleanup_expired`(`repository.py:87`)가 잔류 PENDING 삭제 → 재시도가 라우터를 **다시** 태움

| # | 시나리오 | 방식 | 기대 | 상태 |
|---|---|---|---|---|
| C1 | `mark_completed` 에 예외 주입 (라우터는 **정상 완료**) | fault injection | 500 + 레코드 0건(release 탐) **+ 거래는 1건 잔류** → 재시도 시 라우터 재실행 → **거래 2건** | ✅ |
| C2 | 레코드를 PENDING 으로 되돌린 뒤 같은 키 재요청 | state-based sim | **409 / ID003** — 정당한 재시도가 TTL 동안 막힌다 | ✅ |
| C3 | C2 상태에서 `created_at` 을 TTL 밖으로 밀고 `cleanup_expired` → 같은 키 재요청 | state-based sim | 레코드 삭제 → 락 재획득 → 200 + **거래 2건**. exactly-once 아님 확정 | ✅ |

> **C1 실측이 A9 와 갈린 지점**: A9(라우터 자체가 예외)은 거래 0건이었는데, C1(라우터 성공 후 미들웨어가 예외)은 **거래 1건이 남는다**. `call_next` 가 돌아온 시점엔 `get_db` 의 커밋이 이미 끝나 미들웨어 예외로는 되돌릴 수 없다 = crash window 실재의 직접 증거.
> **용어 정직성(codex 지적 채택)**: 진짜 fault injection 은 C1 뿐이고 C2·C3 는 state-based simulation 이다. 실제 SIGKILL 은 `release` 조차 못 도는데 예외 주입은 `release` 를 타므로, 그 상태는 주입으로 재현되지 않는다. "크래시를 재현했다"가 아니라 "크래시가 남기는 상태에서 출발했다"가 정확한 표현.

**왜 3개로 충분한가** (codex "빠진 crash 지점" 지적에 대한 답)

| 다른 crash 지점 | 수렴하는 최종 상태 |
|---|---|
| `capture_response_body` 중 | 레코드 PENDING 잔류 → **C2** |
| `mark_completed` 후 `commit`(109) 전 | UPDATE 가 롤백돼 PENDING 잔류 → **C2** |
| `release` 전 / 후 commit 전 (5xx·예외 경로) | 둘 다 PENDING 잔류 → **C2** |
| acquire 직후 (라우터 진입 전) | 미커밋 INSERT 가 롤백돼 흔적 0 → 재시도 정상(안전 구간) |

재시도 결과를 가르는 건 crash 시각이 아니라 **남은 레코드 상태**뿐이다. C1(레코드 0 + 거래 잔류)·C2(PENDING 잔류) 두 상태를 덮으면 경우의 수가 닫힌다.

**예상 반격과 답변** (codex 제공 — 면접 대본 재료)

| 반격 | 답변 |
|---|---|
| 실제 SIGKILL 이 아니지 않나 | 맞다. 단일 pytest 프로세스에선 재현 불가라 crash 가 **남기는 상태**를 재현했다. 상태가 같으면 재시도 결과도 같다 |
| 비즈 커밋 시점이 라우터 내부 구현에 의존하는 것 아닌가 | 그래서 C1 을 실측했다 — `call_next` 반환 시점에 이미 커밋돼 있음을 거래 1건 잔류로 확인 |
| TTL 만료 후 중복은 설계 선택 아닌가 | 그렇다. 그래서 버그 리포트가 아니라 **자백**이다. 고치려면 outbox·2PC 급이 필요해 이 규모엔 과하다고 판단했다 |
| DB 직접 update 가 인위적이다 | 인정. 그래서 C1(진짜 주입)과 C2·C3(상태 시뮬)를 표에서 구분해 표기했다 |

## D. 도메인 핵심 🔴 (`tests/domain/`)

**대상 확정 근거 (2026-07-27)** — 후보 4개 중 D3(IDOR)는 사전 전수 스캔으로 강등했다.
`app/domain/*/service.py` 의 public 함수 중 `find_by_id` 후 소속 검증이 없는 곳을 스캔한
결과, 전 도메인이 `household_id != household.id → NOT_FOUND` 를 갖고 있었다. 예외는
`user` 도메인(`detail_user`/`search_by_email`)뿐인데 이건 **멤버 초대용 설계 선택**이다
(라우터에 `인증 가드용` 주석 명시, 응답은 id/email/name/language 만).
→ D3 는 GREEN 이 뻔해 회귀 안전망 가치만 남으므로 후순위.

### D2. 포트폴리오 실현손익/평단 🔴 (`test_portfolio_pnl.py`)

**공개계약** (`portfolio/service.py`)
- `_recompute_realized_pnl` docstring — "거래를 **시간순 replay** 하며 각 SELL 의 실현손익을
  그 시점 평단으로 재박제. 거래 수정/삭제로 평단이 바뀌면 과거 SELL 의 박제값이 틀어지므로"
- `_recalc_item_from_transactions` docstring — "매도 시점 평단으로 원가를 차감하므로
  **매도 후 재매수도 정확히 반영**"

**도출한 불변식(INV)**: 활성 거래 집합이 같으면 각 SELL 의 `realized_pnl` 과 종목의
`quantity`/`avg_price` 는 같다 — 재계산이 언제 트리거됐는지와 무관하게.

| # | 시나리오 | 기대 | 최초 실측 | 상태 |
|---|---|---|---|---|
| D2-1 | 매도 후 재매수 평단 | 잔여원가+신규원가 / 잔여수량 | GREEN | ✅ |
| D2-2 | 과거 BUY 단가 수정 → 과거 SELL 재박제 | 25,000 → 15,000 | GREEN | ✅ |
| **D2-3** | **백데이팅 매수**(매도보다 앞선 `tx_date` 를 뒤늦게 입력) | pnl 0 / 평단 1,500 | **RED — pnl 25,000 / 평단 1,666.67** | ✅ |
| **D2-4** | D2-3 상태에서 **memo 만** 수정 → 재계산만 트리거 | 값 불변 | **RED — 25,000 → 0 으로 변동** | ✅ |

> **찾은 결함(수정 완료)**: 진실 원천이 2개였다.
> | 경로 | 계산 | 순서 기준 |
> |---|---|---|
> | `buy()`/`sell()` | incremental — 그 순간의 `item.avg_price` | **입력 순서**(날짜 무관) |
> | `_recompute_realized_pnl()` | replay — 처음부터 재계산 | **`tx_date asc`** (`repository.py:236`) |
>
> 두 경로가 다른 순서를 보므로 백데이팅 매수 시 값이 갈리고, **금액과 무관한 수정(memo) 한 번**이
> 저장값을 replay 값으로 뒤집었다. C(crash window)와 달리 이건 자백 대상이 아니라 **수정 대상** —
> 고치는 비용이 재계산 호출 한 줄이라 "알고도 안 고쳤다"가 성립하지 않는다.
>
> **수정**: `buy()`/`sell()` 의 incremental 계산을 제거하고 `_recalc_item_from_transactions`
> (replay)로 통일. `sell()` 의 사전 `realized_pnl` 박제도 제거 — replay 가 매도시점 평단으로 채운다.
> 전량매도 판정은 replay 결과(`item.quantity == 0`) 기준으로 변경.

### D1. 계좌 원장 running balance 🔴 (`test_account_ledger.py`)

**공개계약** (`transaction/service.py:81-133` docstring)
- "잔액은 기준 잔액에서 desc 로 역산… 한 칸 옛 거래로 내려갈 때마다 위 행의 `signed_amount` 를
  빼서 그 아래 잔액을 만든다. 페이지 경계는 carry 를 커서에 실어 이어붙인다."
- "year+month 를 주면… 기준점은 그 달 말까지의 누적 잔액이라 **미래 달 거래와 무관하게** 그 달 안에서 잔액이 맞는다."

**착수 전 코드 독해 — D2 같은 결함 가설은 안 나왔다.** D2 는 같은 값을 두 경로가 다른 순서로
계산해 갈렸는데, D1 은 두 경로의 규칙이 일치한다:

| 검토 항목 | 결과 |
|---|---|
| 부호 2경로 — `_signed_amount`(`service.py:422`) vs `sum_for_account`(`repository.py:185`) | INCOME/EXPENSE/TRANSFER 양방향/VALUATION 방향 전부 **규칙 일치** |
| 조회 필터 vs 잔액 합산 필터 | 둘 다 `or_(account_id, to_account_id)` 대칭 |
| 자기 이체(잔액 이중계상 후보) | 스키마(`schema.py:58`) + `_validate_transfer_consistency` 이중 차단 |
| `ValuationDirection` 문자열 비교 | `StrEnum` 이라 DB 문자열과 정상 비교 |

| # | 불변식 | 시나리오 | 상태 |
|---|---|---|---|
| D1-1 | **INV-A 닫힘** | 시작잔액 + 수입·지출·이체 5건 → 끝까지 순회 시 마지막 행 `balance_after − signed_amount == start_balance`, 인접 행끼리도 한 칸씩 연결 | ✅ GREEN |
| D1-2 | **INV-B 페이지 불변** | 거래 6건, `limit=100`(1페이지) vs `limit=2`(3페이지)의 `(id, balance_after)` 열 동일 | ✅ GREEN |
| D1-3 | **INV-C 월 기준점** | 전월 2 + 당월 2 상태에서 조회 → **다음 달 거래 2건 추가 후 재조회** → 당월 잔액 불변 | ✅ GREEN |
| D1-4 | **INV-D 이체 부호** | 한 이체가 출금 원장 `−amount` / 입금 원장 `+amount`, 같은 `tx.id` 양쪽 1행씩 | ✅ GREEN |
| D1-5 | **INV-E 평가조정 부호** | 수동자산 통장 VALUATION INCREASE `+` / DECREASE `−`, 잔액 누적 | ✅ GREEN |

> **소스 결함 0.** 잔액이 저장값이 아니라 계산 결과인데도 역산이 정확히 닫혔다.
> **D1-2 의 페이지 수 단언이 핵심 장치**: `paged_pages == 3` 을 단언하지 않으면 커서가 한 페이지만
> 돌고도 "페이지 불변"이 통과해버린다 — 경로를 실제로 탔음을 강제한다(A11-nc 와 같은 정신).
> **D2 와의 대비**: 같은 "값을 두 곳에서 계산" 구조인데 D1 은 규칙이 일치해 안 갈렸다.
> 결함을 가른 건 구조가 아니라 **두 경로가 같은 순서·같은 규칙을 보는가**였다.

### 남은 후보 (미착수)

| # | 시나리오 | 비고 |
|---|---|---|
| D3 | household IDOR | 위 스캔 근거로 후순위 (회귀 안전망) |
| D4 | 종목 수량/평단 상태 전이 (매도>매수 차단, 소멸/부활) | D2 수정으로 replay 경로 일원화됨 — 경계 재확인 가치 |
| D1-6 | 깨진 커서 fallback (`_split_ledger_cursor`/`_cursor_after` 파싱 실패 시 조용히 1페이지 반복) | D1 스코프 밖으로 뺀 엣지 — `service.py:447,450-451` 미커버 |
