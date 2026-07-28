# 05. fixed·account_snapshot — "고정지출 메타" 와 "매월 박제되는 과거"

> 04에서 두 개의 약속을 남겼다. ① `FIXED_EXPENSE` 거래는 `fixed_expense_id` 로 **고정지출(FixedExpense)** 에 매달린다(04 §4-1) — 그 FixedExpense 가 뭔지. ② 03 §4-5에서 "지난 달들의 추이는 매월 1일 스케줄러가 박제한 **스냅샷(AccountSnapshot)** 에서 읽는다"고 했다 — 그 박제가 어떻게 일어나는지. 이 문서가 둘을 완결한다. 백미 셋: ① **고정지출은 금액을 안 들고 있다**(메타만, 실제 금액은 거래 집계), ② **잔액은 계산하지만 "과거 잔액"은 박제한다**(이 앱의 핵심 모순 해소), ③ **스냅샷의 두 가지 삭제** — hard(재생성용)와 soft(통장 cascade용)가 다르다.

> **이 문서 읽는 법:** §4(공통 메커니즘)에 메타·박제 파이프라인·멱등성·두 삭제·스케줄러 같은 "공유 로직"을 한 번 깊게 정리했다. §5는 fixed 6개 + snapshot 2개 API + **스케줄러 잡 1개**를 요청(혹은 트리거)부터 결과까지 한 줄기로 따라가며 공통 로직은 `→ §4-x` 로 참조한다.

---

## 1. 이 도메인 한마디

**고정지출(FixedExpense)** 은 "매달 나가는 항목의 정의" — 월세·통신비·구독료처럼 이름·결제일만 등록해 두는 **꼬리표**다. 실제 얼마 썼는지는 거기 매달린 거래들의 합. **월간 스냅샷(AccountSnapshot)** 은 매월 1일 자동으로 그 시점 통장 잔액과 월 수입/지출을 **박제(저장)** 해, "계산으로는 복원 못 하는 과거"를 보존한다. 하나는 "미래에 나갈 것의 틀", 하나는 "지나간 것의 사진".

---

## 2. 들어가기 전 (개념 콕)

| 개념 | 한마디 |
|---|---|
| **메타(meta) vs 실적** | FixedExpense 는 "월세, 매달 25일"이라는 **정의**만. 실제 낸 금액은 거래에서 집계(§4-1). |
| **박제(snapshot)** | 매월 1일 그 시점 잔액·월합계를 **그대로 저장**. 03의 "잔액은 계산" 원칙의 유일한 예외(§4-2). |
| **왜 박제하나** | 거래는 수정·삭제된다. 과거 잔액을 매번 재계산하면 "그때 실제로 얼마였나"가 바뀐다. 박제하면 고정(§4-2). |
| **catch-up** | 서버가 1일에 안 떠 박제를 놓쳐도, 다음 실행 때 빠진 달을 거슬러 채운다(§4-3). |
| **upsert(멱등)** | 같은 달을 두 번 박제해도 중복이 안 생긴다 — 기존 걸 지우고 다시 만든다(§4-3). |
| **hard vs soft delete** | 박제는 파생 데이터라 재생성 시 **hard delete**(흔적X). 통장 삭제 cascade 시엔 **soft delete**(§4-4). |
| **advisory lock** | 서버가 여러 대여도 월간 박제 잡이 한 번만 돌게 PostgreSQL 락으로 막는다(§4-6). |

---

## 3. 데이터 모델

### 3-1. `fixed_expenses` — 고정지출 메타 (금액 없음)

```python
# app/domain/fixed/model.py:9
class FixedExpense(BaseEntity):
    household_id: Mapped[UUID]      # 소속 가계부 (논리 FK)
    name:         Mapped[str]       # String(100) — "월세", "넷플릭스"
    day_of_month: Mapped[int]       # 결제 예정일 1~31
    category_id:  Mapped[UUID|None] # 분류 연결 (논리 FK, nullable)
    color:        Mapped[str|None]  # String(7)
    icon:         Mapped[str|None]  # String(50)
    sort_order:   Mapped[int]       # 화면 정렬
    is_archived:  Mapped[bool]      # 보관 여부 (03·04와 같은 개념)
```

```python
# app/domain/fixed/model.py:10  — 클래스 docstring (설계 의도가 코드에 박혀 있음)
"""금액은 보유하지 않음. 실제 지출 내역은 transactions 에 fixed_expense_id 로
매핑되어 기록되고, 월별 사용액은 거래 합산으로 구함."""
```

> **`amount` 컬럼이 없다.** 처음엔 있었지만 alembic `a9668f7687a9`(drop_fixed_expenses_amount)에서 제거됐다. 이유: "월세 50만원"이라고 박아둬도 실제로는 49만·51만이 나갈 수 있다. **예정 금액**과 **실제 금액**이 어긋나면 어느 게 진실이냐는 문제가 생긴다. 그래서 금액은 안 들고, 실제 거래 합계만 진실로 본다(03의 "잔액 안 들고 계산"과 같은 철학). FixedExpense 는 "이름·결제일·분류"라는 틀만 제공.

### 3-2. `account_snapshots` — 월말 박제 (계산의 예외)

```python
# app/domain/account_snapshot/model.py:11
class AccountSnapshot(BaseEntity):
    account_id:            Mapped[UUID]     # 어느 통장 (논리 FK)
    snapshot_date:         Mapped[date]     # 박제 기준일 — 항상 "그 달 1일"
    balance:               Mapped[Decimal]  # ★ 그 시점 통장 잔액 박제값
    monthly_income:        Mapped[Decimal]  # 그 달 수입 합 (캐시)
    monthly_expense:       Mapped[Decimal]  # 그 달 지출 합 (캐시)
    monthly_fixed_expense: Mapped[Decimal]  # 그 달 고정지출 합 (캐시)
```

```python
# app/domain/account_snapshot/model.py:23  — 캐시 컬럼의 이유
"""그 달 흐름 캐시 — 매번 transactions 합산 안 하려고 박제 시점에 같이 박음."""
```

```python
# app/domain/account_snapshot/model.py:15  — 인덱스 (조회 패턴)
Index("idx_snapshots_account_date", "account_id", text("snapshot_date DESC"))  # 계좌별 시간순
Index("idx_snapshots_date", text("snapshot_date DESC"))
```

> **이게 03 §4-5의 "박제된 과거"다.** 03에서 통장 잔액은 절대 저장 안 하고 계산한다고 했는데, AccountSnapshot 의 `balance` 는 그 예외 — **저장한 잔액**이다. 모순이 아니라 역할 분담: "현재 잔액"은 거래가 바뀌면 따라 바뀌어야 하니 계산, "과거 어느 시점 잔액"은 그때의 사진이라 고정. `monthly_income/expense/fixed_expense` 는 매번 거래를 다시 합산하지 않으려는 **캐시**다(04 §4-2의 `sum_by_account_for_month` 가 박제 시점에 한 번 계산해 넣는다). **unique 제약은 DB에 없다** — "같은 통장+같은 달" 중복 방지는 코드(멱등성, §4-3)가 책임진다.

### 3-3. 두 도메인의 위치

| 도메인 | 무엇 | 누가 읽나 |
|---|---|---|
| FixedExpense | 고정지출 정의(메타) | 거래 입력 폼(04 form-options), `/fixed/monthly-summary` |
| AccountSnapshot | 월말 잔액·흐름 박제 | `/account/report`(03 §4-5), `/account-snapshot/yearly`, wealth(자산추이, →07) |

---

## 4. 공통 메커니즘

### 4-1. 메타 vs 실적 — 고정지출 금액은 거래에서 집계

FixedExpense 는 금액이 없으니(§3-1), "이번 달 월세 얼마 냈나"는 거래를 합산해 만든다:

```python
# app/domain/fixed/service.py:189  get_monthly_summary
rows = await TransactionRepository(db).sum_by_fixed_for_month(household.id, year, month)
items = [FixedMonthlyUsage(fixed_expense_id=fid, used=total) for fid, total in rows]
```
그 합산 쿼리는 04에서 본 것:
```python
# app/domain/transaction/repository.py:366  sum_by_fixed_for_month
# fixed_expense_id 별 그 달 합계 — EXPENSE 와 FIXED_EXPENSE 둘 다 포함
.where(tx_type.in_([EXPENSE, FIXED_EXPENSE]), fixed_expense_id IS NOT NULL, ...)
.group_by(fixed_expense_id)
```

> **연결 방향에 주의.** 실제 ForeignKey 는 **거래 쪽**에 있다 — `transactions.fixed_expense_id → fixed_expenses.id`(04 §3-2, `ondelete="SET NULL"`). fixed 도메인은 거래를 import 하지도, FK 를 갖지도 않는다. "거래가 고정지출을 가리킨다"는 단방향. 그래서 고정지출 삭제 시 매핑된 거래는 DB 가 자동으로 `fixed_expense_id` 를 NULL 로 끊는다(§4-4).

### 4-2. 박제 파이프라인 — 매월 잔액·흐름을 사진 찍는다

스케줄러가 매월 1일 부르는 진입점:

```python
# app/domain/account_snapshot/service.py:32  create_monthly_snapshots_for_all
target_date = _target_month()                               # 박제 기준 = 지난달 1일
months = [_shift_months(target_date, -i) for i in range(12)] # 최근 12개월 (catch-up 범위)
upsert_months = {target_date, _shift_months(target_date, -1)}# 최근 2개월만 덮어씀
for h in households:                                          # 모든 가계부 순회
    ... _build_and_save_snapshot(db, h, month, replace=exists)
```

실제 박제 한 통장 단위:
```python
# app/domain/account_snapshot/service.py:198  _build_and_save_snapshot
for a in accounts:                                  # is_archived 제외한 활성 통장
    summary = await _calc_balance(tx_repo, a, db)   # ① 잔액 — account 도메인 공식 재사용(03 §4-2)
    monthly = await tx_repo.sum_by_account_for_month(a.id, year, month)  # ② 월 흐름(04 §4-2)
    snapshots.append(AccountSnapshot(
        account_id=a.id, snapshot_date=target_date,
        balance=summary.balance,                    # 계산값을 "박제값"으로 굳힘
        monthly_income=monthly["income"],
        monthly_expense=monthly["expense"],
        monthly_fixed_expense=monthly["fixed_expense"],
    ))
await AccountSnapshotRepository(db).save_all(snapshots)      # 일괄 INSERT
await snapshot_household_portfolio(db, household, target_date, replace=replace)  # ③ 종목 박제(→06)
```

> **박제는 "계산을 굳히는" 행위다.** ① 잔액은 03의 `_calc_balance` 를 **그대로 호출**해 계산한 뒤 그 값을 저장한다 — 계산 로직이 한 군데(account 도메인)에만 있도록. ② 월 흐름은 04의 `sum_by_account_for_month`. ③ 투자 통장의 종목 평가액은 portfolio 도메인이 별도 박제(`PortfolioValueHistory`, →06) — AccountSnapshot 은 통장 잔액·현금흐름만, 종목은 portfolio 책임으로 분리.

### 4-3. catch-up + upsert — "놓쳐도 채우고, 두 번 돌려도 안전"

```python
# app/domain/account_snapshot/service.py:52
oldest = await repo.oldest_active_month(h.id)       # 데이터 시작점
catchup_floor = oldest if oldest else target_date
for month in months:                                # 최근 12개월
    if month < catchup_floor:        continue       # 데이터 시작 전은 안 채움
    exists = await repo.has_active_for_month(h.id, month)
    if exists and month not in upsert_months: continue  # 과거 박제는 고정 — 안 건드림
    await _build_and_save_snapshot(db, h, month, replace=exists)  # 없으면 채우고/최근2개월이면 덮어씀
```

세 갈래로 갈린다:

| 달 | 상태 | 동작 |
|---|---|---|
| 최근 2개월(지난달·그전달) | `upsert_months` | **항상 재계산해 덮어씀** — 늦게 입력된 거래까지 반영 |
| 그 이전 ~ 데이터 시작 | 박제 없음 | **catch-up**: 빠진 달만 채움 |
| 그 이전 ~ 데이터 시작 | 박제 있음 | **보존** — 과거는 고정, 안 건드림 |
| 데이터 시작 전 | — | 무시 |

> **왜 최근 2개월만 덮어쓰나?** 거래는 보통 며칠 안에 입력된다. "5월 거래를 6월 중순에 뒤늦게 추가"하는 일은 흔하니 최근 두 달은 재계산. 하지만 1년 전 박제까지 매번 다시 계산하면 비싸고, 그쯤이면 거래가 더 안 들어오니 고정한다. **멱등성(upsert)** 은 `replace=exists` → 기존 걸 지우고(§4-4) 다시 INSERT 하는 방식. 그래서 스케줄러가 같은 달 두 번 돌거나, 사용자가 수동 박제를 눌러도 중복 row 가 안 생긴다.

### 4-4. 스냅샷의 두 가지 삭제 — hard vs soft

박제 데이터는 삭제가 **두 경로**고 방식이 다르다:

```python
# app/domain/account_snapshot/repository.py:86  delete_for_household_month — upsert 재생성용
"""박제는 파생 데이터라 soft delete 대신 hard delete — DELETED 행이 안 쌓임."""
stmt = delete(AccountSnapshot).where(... snapshot_date == month_first)  # 진짜 DELETE
```
```python
# app/domain/account_snapshot/repository.py:101  soft_delete_by_account_id — 통장 cascade용(03 §4-4)
.values(data_stat_cd=DataStatus.DELETED)   # soft delete
```

| | hard delete | soft delete |
|---|---|---|
| 함수 | `delete_for_household_month`(:86) | `soft_delete_by_account_id`(:101) |
| 트리거 | 월 재박제(upsert) | 통장 삭제 cascade(03 §4-4) |
| 이유 | 파생 데이터라 재생성하면 그만 — DELETED 행 안 쌓이게 진짜 삭제 | 통장과 운명 같이 — 다른 soft-delete 와 일관 |

> 일반 도메인(통장·거래·카테고리)은 전부 soft-delete 가 기본이었다(03·04). 스냅샷만 예외적으로 **재생성 경로에선 hard delete** — 어차피 거래로부터 다시 계산되는 파생물이라 "지운 기록"을 남길 필요가 없고, 매월 upsert 하면 DELETED 행이 무한정 쌓이기 때문.

### 4-5. 조회 범위 정규화 — 자산추이와 같은 축

```python
# app/domain/account_snapshot/service.py:90  resolve_snapshot_range
"""to=지난달(미지정 시), from=to−11개월. 모두 그달 1일.
   배분추이(wealth)와 연간추이(snapshot)가 같은 축을 쓰도록 공통 사용."""
```
> 기본 조회 구간은 **최근 12개월**(03의 report 와 같은 기본값). `_shift_months`(:150)가 연도 경계를 안전하게 넘긴다(12월→1월). wealth 도메인(자산 배분 추이, →07)도 같은 함수를 써서 두 화면의 x축이 어긋나지 않는다.

### 4-6. 스케줄러 공통 — advisory lock 으로 한 번만

월간 박제는 5개 스케줄 잡 중 하나다(01 인프라):

```python
# app/core/scheduler.py:90  잡 등록
scheduler.add_job(jobs.create_monthly_snapshots_job,
                  CronTrigger(day=1, hour=0, minute=30, timezone=KST))  # 매월 1일 00:30 KST
```
```python
# app/core/scheduler.py:32  run_locked_job — 모든 잡 공통 보일러플레이트
async with async_session() as session:           # 자체 세션 (요청 DI 와 분리)
    async with session.begin():                  # 명시 트랜잭션
        if not await try_advisory_lock(session, job_name):  # PG advisory xact lock
            return                               # 락 못 잡으면 조용히 skip (다른 인스턴스가 잡음)
        await fn(session)
```

스케줄러 5잡 전경:

| 잡 | 시각(KST) | 역할 |
|---|---|---|
| `refresh_usd_krw` | 매일 09:00 (월–금) | 환율 갱신 (→07) |
| `refresh_us_prices` | 매일 09:10 (화–토) | 미장 시세 (→06·07) |
| `refresh_kr_prices` | 매일 16:10 (월–금) | 국장 시세 |
| `cleanup_idempotency` | 매시간 | 멱등성 레코드 만료 정리 |
| **`create_monthly_snapshots`** | **매월 1일 00:30** | **월간 자산 박제(이 문서)** |

> **왜 advisory lock 인가?** 서버를 여러 대 띄우면(스케일아웃) 같은 잡이 인스턴스마다 동시에 깨어난다. 월간 박제가 동시에 두 번 돌면 중복·경합이 난다. PostgreSQL 의 `pg_try_advisory_xact_lock` 으로 "한 명만 통과, 나머지는 skip"을 보장한다 — 트랜잭션 끝나면 자동 해제라 락 누수도 없다. 00:30 에 도는 건 "전월 말일 종가가 시세에 반영된 뒤"라는 타이밍(jobs.py:48 주석).

---

## 5. 엔드포인트별 풀 트레이스

fixed 는 `CurrentHousehold` 를 받는다(→02 §4). snapshot 의 자동 박제는 API 가 아니라 **스케줄러 트리거**라 §5-C 에 따로 둔다. 실제 URL은 `root_path="/api"` + prefix.

### 5-A. 고정지출 (`/fixed`) — 6개

#### GET /fixed/list — 목록 (무한 스크롤)
```
요청  GET /api/fixed/list?limit=30&searchTerm=&isArchived=   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:26  list_fixed_expenses
      household: CurrentHousehold, q: FixedListQuery → limit 1~200(schema.py)
─[2] 서비스        service.py:47  list_fixed_expenses_cursor
      repo.list_by_cursor → frst_reg_dt DESC, limit+1 (관리 페이지용)
      CategoryRepository.find_by_ids → 카테고리명/색/아이콘 batch 조인 (N+1 차단)
      count_search → total_count,  next_cursor = "{frst_reg_dt}|{id}"
─[3] 응답 조립     service.py:84  _build_response × N → FixedResponse(카테고리 조인 필드 포함)
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(CursorPage[FixedResponse])
```
> 내부용 `list_fixed_expenses`(service.py:25, sort_order 정렬)는 별도 — 04의 거래 입력 폼(`get_form_options`)이 `is_archived=False` 로 호출해 "활성 고정지출 선택지"를 채운다.

#### POST /fixed/create — 생성
```
요청  POST /api/fixed/create  {name, dayOfMonth, categoryId?, color?, icon?, sortOrder?}  + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:43  create_fixed_expense
      FixedCreateRequest._validate(schema.py): name 1~100, day_of_month 1~31, color ≤7
─[2] 서비스        service.py:92  create_fixed_expense
      category_id 주면 _validate_category(service.py:221): 같은 household active 카테고리인지
      sort_order = req값 ?? (repo.max_sort_order(household.id)+1)
      FixedExpense(... is_archived=False, ACTIVE) → repo.save → add+flush
─[3] 응답 조립     service.py:117  _build_response → FixedResponse
─[4] 트랜잭션 종료  get_db — commit (INSERT 확정)
응답  ApiResponse.ok(FixedResponse)
```

#### GET /fixed/detail/{fixed_id} — 단건
```
요청  GET /api/fixed/detail/{id}   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:54  household: CurrentHousehold
─[2] 서비스        service.py:173  get_fixed_detail
      find_by_id(ACTIVE만) → 없거나 / household_id 불일치 → NOT_FOUND
      카테고리 조인
─[3] 응답 조립     _build_response → FixedResponse
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(FixedResponse)
```

#### PUT /fixed/update/{fixed_id} — 수정 (보관 토글 포함)
```
요청  PUT /api/fixed/update/{id}  {name?, dayOfMonth?, categoryId?, …, isArchived?}  + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:65  FixedUpdateRequest._validate(schema.py): name 주면 1~100, day 1~31, color ≤7
─[2] 서비스        service.py:125  update_fixed_expense
      find_by_id + household_id 가드 → NOT_FOUND
      category_id 바뀌면 _validate_category
      None 아닌 필드만 부분 수정 (is_archived 포함 → 보관/해제)
      db.flush
─[3] 응답 조립     _build_response (수정 후)
─[4] 트랜잭션 종료  get_db — commit (UPDATE 확정)
응답  ApiResponse.ok(FixedResponse)
```

#### DELETE /fixed/delete/{fixed_id} — soft-delete (거래는 DB가 NULL 처리)
```
요청  DELETE /api/fixed/delete/{id}   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:77  household: CurrentHousehold
─[2] 서비스        service.py:160  delete_fixed_expense
      find_by_id + household_id 가드 → NOT_FOUND
      data_stat_cd = DELETED 만 (차단 없음)
      ※ 매핑된 거래의 fixed_expense_id 는 DB FK(ondelete SET NULL)가 자동으로 끊음   → §4-1
─[3] 응답 조립     반환값 없음 (None)
─[4] 트랜잭션 종료  get_db — commit
응답  ApiResponse.ok()
```
> 04의 카테고리 삭제는 거래 `category_id` 를 그대로 뒀다(논리 FK, orphan). 여기 고정지출은 **실제 FK** 라 DB 가 `SET NULL` 로 끊는다 — 결과는 비슷(거래는 살아남고 매핑만 사라짐)하지만 메커니즘이 다르다: 카테고리=손 안 댐, 고정지출=DB 자동 NULL.

#### GET /fixed/monthly-summary — 고정지출별 이번 달 사용액
```
요청  GET /api/fixed/monthly-summary?month=2026-06   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:88  get_monthly_summary
      month 파싱: "YYYY-MM"(1~12 검증), 없으면 KST 이번달    아니면 BAD_REQUEST
─[2] 서비스        service.py:189  get_monthly_summary
      TransactionRepository.sum_by_fixed_for_month → fixed_expense_id별 그달 합계  → §4-1
      (EXPENSE + FIXED_EXPENSE, fixed_expense_id 매핑된 것만)
─[3] 응답 조립     service.py:196  FixedMonthlySummaryResponse(month, items[{fixed_expense_id, used}])
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(FixedMonthlySummaryResponse)
```
> 프론트는 이 `used` 와 고정지출 메타(이름·결제일)를 합쳐 "이번 달 고정비 진행률"을 그린다 — 예: "월세 항목에 50만 썼고 결제일은 25일".

### 5-B. 월간 스냅샷 API (`/account-snapshot`) — 2개

#### POST /account-snapshot/create — 수동 박제 (지난달, upsert)
```
요청  POST /api/account-snapshot/create   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:19  create_snapshot  (household: CurrentHousehold)
─[2] 서비스        service.py:71  create_target_month_snapshot
      target_date = _target_month() (지난달 1일)
      exists = has_active_for_month → _build_and_save_snapshot(replace=exists)   → §4-2·§4-3
      (replace 면 delete_for_household_month hard delete 후 재INSERT)             → §4-4
      종목 박제도 함께(snapshot_household_portfolio)
─[3] 응답 조립     service.py:248  _build_month → SnapshotMonth(total_* + accounts[])
─[4] 트랜잭션 종료  get_db — commit
응답  ApiResponse.ok(SnapshotMonth)
```
> 자동 박제(스케줄러)가 1일에 안 돌았거나, 뒤늦은 거래로 지난달 수치가 틀어졌을 때 사용자가 직접 다시 찍는 버튼. 같은 달 몇 번 눌러도 upsert 라 안전(§4-3).

#### GET /account-snapshot/yearly — 월별 자산 추이
```
요청  GET /api/account-snapshot/yearly?fromDate=&toDate=   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:29  yearly_snapshots  (SnapshotYearlyQuery: fromDate/toDate)
─[2] 서비스        service.py:107  get_yearly_snapshots
      resolve_snapshot_range → 기본 최근 12개월(그달 1일 정규화)                  → §4-5
      repo.find_by_household_and_range (account JOIN 으로 household 필터)
      AccountRepository.find_by_ids → 통장명 보충(삭제된 통장은 "(삭제됨)")
      snapshot_date 별 그룹 → _build_month 로 월별 total_* 집계
      has_active_for_month(지난달) → target_month_saved (지난달 박제됐나 플래그)
─[3] 응답 조립     service.py:134  SnapshotYearlyResponse(months[], target_month_saved, target_month_date)
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(SnapshotYearlyResponse)
```
> `target_month_saved` 가 false 면 프론트가 "지난달 박제가 아직 없으니 수동 박제(5-B 위)를 누르세요" UI 를 띄울 수 있다.

> **03 의 `/account/report` 와 다른 점:** report 는 통장 **한 개**의 추이(`find_by_account_and_range`, repo:67)고, yearly 는 가계부 **전체** 통장 합산 추이(`find_by_household_and_range`, repo:32). 같은 박제 테이블을 단일 통장 단위 vs 가계부 단위로 다르게 읽는다.

### 5-C. 스케줄러 잡 트레이스 — `create_monthly_snapshots` (API 아님)

```
트리거  매월 1일 00:30 KST  CronTrigger(day=1, hour=0, minute=30)        scheduler.py:90
─[1] 진입         jobs.py:47  create_monthly_snapshots_job
      run_locked_job("create_monthly_snapshots", _run)                  scheduler.py:32
      자체 세션 + session.begin() + advisory lock 시도                   → §4-6
      락 실패(다른 인스턴스가 잡음) → 조용히 skip
─[2] 본작업       service.py:32  create_monthly_snapshots_for_all
      target = 지난달, 최근 12개월 순회, 최근 2개월 upsert / 나머지 catch-up   → §4-3
      가계부마다: 활성통장 _calc_balance(03) + sum_by_account_for_month(04) 박제  → §4-2
      종목 박제(portfolio, →06) 동반
─[3] 종료         예외 없으면 트랜잭션 commit (advisory lock 자동 해제)
      예외 시 logger.exception + raise (스케줄러가 다음 trigger 대기)        scheduler.py:50
결과  account_snapshots 에 (가계부×통장×월) row 신규/갱신
```

---

## 6. 데이터 흐름 (도메인 큰 그림)

```
[고정지출 — 메타]
  거래 입력(04) ──fixed_expense_id 매핑──▶ transactions
                                              │
  /fixed/monthly-summary ◀── sum_by_fixed_for_month (거래 집계) ──┘   (§4-1, 금액은 거래에서)
  /fixed/* CRUD ──▶ fixed_expenses (이름·결제일·분류 메타만)

[월간 스냅샷 — 박제]
  스케줄러(매월1일 00:30) ──advisory lock──▶ create_monthly_snapshots_for_all
                                              │  (§4-2·§4-3 catch-up+upsert)
        ┌─────────────────────────────────────┤
   _calc_balance(03)              sum_by_account_for_month(04)
   = 그 시점 잔액                   = 그 달 수입/지출/고정지출
        └──────────────┬──────────────────────┘
                  account_snapshots 에 박제 (balance + monthly_* 캐시)
                        │
        ┌───────────────┼────────────────────────┐
  /account/report(03)   /account-snapshot/yearly   wealth 자산추이(→07)
  통장 1개 추이          가계부 전체 추이             배분 추이
  (find_by_account)     (find_by_household)
```

> 스냅샷은 **거래(04) → 잔액(03) 계산을 한 번 굳혀** 여러 추이 화면(report·yearly·wealth)에 공급하는 "과거 저장소". 고정지출은 반대로 거래에 **매달려** 실적을 집계당하는 "메타".

---

## 7. 이 문서에서 꼭 기억할 규칙

1. **고정지출은 금액을 안 들고 있다**(§3-1, §4-1). 이름·결제일·분류 메타만. 실제 사용액은 `sum_by_fixed_for_month` 로 거래 집계. `amount` 컬럼은 alembic 에서 제거됨.
2. **연결 FK 는 거래 쪽에 있다**(§4-1). `transactions.fixed_expense_id → fixed_expenses.id`(SET NULL). 고정지출 삭제 시 거래는 DB 가 자동 NULL — 카테고리(논리FK, 손 안 댐, 04 §4-6)와 메커니즘이 다르다.
3. **잔액은 계산이지만 과거 잔액은 박제**(§3-2, §4-2). AccountSnapshot.balance 가 03의 "잔액 저장 안 함" 원칙의 유일한 예외. 거래가 바뀌어도 과거 사진은 고정.
4. **박제는 catch-up + upsert**(§4-3). 최근 2개월은 항상 덮어쓰고(늦은 거래 반영), 그 이전은 빈 달만 채우고 고정. 멱등 — 두 번 돌아도 안전.
5. **스냅샷의 두 삭제**(§4-4): 재생성은 **hard delete**(파생 데이터, 흔적 안 남김), 통장 cascade 는 **soft delete**. 일반 도메인의 soft-delete 기본과 다른 예외.
6. **월간 박제는 스케줄러 5잡 중 하나**(§4-6). 매월 1일 00:30 KST, advisory lock 으로 다중 인스턴스에서 한 번만 실행. `_calc_balance`(03)·`sum_by_account_for_month`(04)를 재사용 — 계산 로직은 원 도메인에만.
7. fixed API 는 `CurrentHousehold` + `household_id` 일치 검사. 박제 잔액·흐름 계산은 전부 활성·비보관 통장만 대상.

---

## 다음 문서
➡ **`06-portfolio-trading.md`** — 가장 큰 도메인(2216줄). 투자 통장의 **주식 매매(BUY/SELL)** 와 보유 종목(PortfolioItem), 그리고 §4-2에서 "종목 평가액은 portfolio 가 따로 박제한다"던 `PortfolioValueHistory` 의 정체. 03 §4-2의 INVESTMENT 잔액 공식(현금 + 보유종목 평가액)이 여기서 완결된다.
