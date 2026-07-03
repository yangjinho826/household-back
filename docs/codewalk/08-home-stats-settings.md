
# 08. home · stats · settings — "앞의 일곱 도메인이 만든 데이터를, 화면 하나로 합쳐 뿌린다"

> 02~07이 데이터를 **쌓았다.** 계좌 잔액(03)·거래 원장(04)·고정지출(05)·투자 평가액(06)·환율/자산배분(07). 이 문서의 셋은 **아무것도 쌓지 않는다** — 그 데이터를 **읽어서 화면 하나로 조립**할 뿐이다. 이 문서의 백미 셋 — ① **세 도메인 모두 테이블이 없다** — 07 wealth처럼 `model.py`가 아예 없는 **순수 조회/집계 레이어**. ② **home은 재구현이 0** — account·transaction·stats 서비스를 그대로 호출해 한 응답에 묶는 "얇은 집계 레이어"다(홈 진입 = API 1호출). ③ **stats만 자기 로직이 있다** — 카테고리별 합계에 `ratio`(같은 kind 내 max 대비)를 매기고, **삭제된 카테고리의 과거 거래까지** 집계에 남긴다. 시리즈의 **소비 끝단**이다.

> **이 문서 읽는 법:** 셋 다 엔드포인트가 **GET 1개씩, 총 3개**뿐이라 §5 트레이스가 짧고 선명하다. §4에 "위임 집계 패턴"·"stats 3단 집계"·"삭제 카테고리 처리"를 한 번 정리하고, §5는 거기를 `→ §4-x`로 참조한다. 앞 문서들이 `(→08)`로 넘긴 약속들(04 §5 "통계", 04 §6 "달력/통계")의 **정본이 여기**다.

---

## 1. 이 도메인 한마디

**화면 한 장을 그리는 데 필요한 여러 도메인의 숫자를, 한 번의 API 호출로 묶어준다.** home은 홈 대시보드용 — 총자산 + 통장 목록 + 최근 거래 10건 + 이번 달 통계를 **한 응답**으로. stats는 그 "이번 달 통계" 본체 — 카테고리별 수입/지출을 집계해 차트용 비율까지. settings는 설정 화면용 — 각 도메인이 몇 건인지 `COUNT(*)`만 5번. 셋 다 **자기 테이블 없이** 앞 도메인들의 서비스·repository를 호출해 조립하는 **읽기 전용 집계 도메인**이다.

---

## 2. 들어가기 전 (개념 콕)

| 개념 | 한마디 |
|---|---|
| **집계/조회 전용 도메인** | home·stats·settings 폴더엔 `router.py`·`service.py`·`schema.py`뿐 — `model.py`가 없다(§3). 07 wealth와 같은 구조. 자기 데이터를 저장하지 않고 남의 데이터를 **읽어 조립**만 한다. |
| **위임 집계 (delegation)** | home·settings는 로직을 **재구현하지 않는다.** 이미 있는 `account_service`·`transaction_service`·`stats_service`·각 repo를 그대로 호출해 결과만 묶는다(§4-1). "바퀴 재발명 금지"의 코드판. |
| **BFF성 1호출** | 홈/설정 화면이 도메인마다 따로 API를 때리는 대신 **한 번에** 받는다(`/home/overview`, `/settings/overview`). 프론트 왕복(round-trip)을 줄이는 화면-지향 엔드포인트. |
| **`ratio` 정규화** | stats는 카테고리별 금액에 `ratio`(0~1.00)를 매긴다 — **같은 kind(수입/지출) 안에서 최대 금액 대비 비율**. 차트 막대 길이용이지 전체 대비 점유율이 아니다(§4-2). |
| **삭제 카테고리 보존** | stats는 `find_by_ids`(필터 없는 조회)를 써서 **soft-delete된 카테고리의 과거 거래도** 집계에서 누락시키지 않는다(§4-3). 원장(04)은 카테고리가 지워져도 그 거래 금액은 남아야 하니까. |
| **소비 끝단** | 이 셋은 시리즈에서 데이터를 **읽기만** 하는 종착지. home이 06·07이 채운 투자·자산 숫자까지 한 화면에 모으며 산책이 닫힌다. |

---

## 3. 데이터 모델 — **셋 다 자체 테이블 없음**

세 도메인 모두 `model.py`가 없다. 07 wealth에 이어 **테이블 없이 동작하는** 도메인이 셋 더 있는 셈. 응답 스키마(`schema.py`)만 존재한다.

### 3-1. home — `HomeOverviewResponse` (4도메인 합성)

```python
# app/domain/home/schema.py:10
class HomeOverviewResponse(CamelBaseModel):
    total_balance:       Money                        # Σ 통장 잔액 (03)
    accounts:            list[AccountResponse]         # 통장 목록 그대로 (03)
    recent_transactions: list[TransactionResponse]    # 최근 10건 (04)
    stats:               MonthlyStatsResponse          # 이번 달 통계 (아래 3-2)
    year:  int
    month: int
```
> **응답 타입부터가 4도메인의 조립.** `AccountResponse`(03)·`TransactionResponse`(04)·`MonthlyStatsResponse`(stats)를 **그대로 필드로 담는다** — home은 새 표현형을 만들지 않고 남의 스키마를 재사용한다. 이게 "얇은 집계 레이어"의 증거.

### 3-2. stats — `MonthlyStatsResponse` + `CategoryStatsItem`

```python
# app/domain/stats/schema.py:19
class MonthlyStatsResponse(CamelBaseModel):
    year: int; month: int
    monthly_income:   Money        # 이번 달 수입 합
    monthly_expense:  Money        # 이번 달 지출 합 (EXPENSE + FIXED_EXPENSE)
    monthly_transfer: Money        # 이번 달 이체 합
    by_category: list[CategoryStatsItem]   # 카테고리별 상세 (차트용)

# app/domain/stats/schema.py:7
class CategoryStatsItem(CamelBaseModel):
    category_id: UUID
    name: str; icon: str | None; color: str | None   # 카테고리 표시용
    is_income: bool                                    # 수입/지출 구분
    amount: Money
    ratio:  Rate       # 0.00~1.00 — 같은 kind 내 max 대비 (§4-2)
```
> stats는 셋 중 **유일하게 자기 로직이 있는** 도메인이지만, 그 로직도 결국 transaction repo의 집계 쿼리(§4-2) 위에 얹은 가공이다. 테이블은 여전히 없다.

### 3-3. settings — `SettingsOverviewResponse` (숫자 5개)

```python
# app/domain/settings/schema.py:4
class SettingsOverviewResponse(CamelBaseModel):
    account_count:     int    # 통장 수 (03)
    category_count:    int    # 카테고리 수 (04)
    fixed_count:       int    # 고정지출 수 (05)
    transaction_count: int    # 거래 수 (04)
    portfolio_count:   int    # 보유 종목 수 (06)
```
> 설정 화면의 "통장 3개 · 카테고리 12개 · 고정지출 5개…" 같은 배지 숫자. 각 도메인 repo의 `count_*`를 한 번씩 부른 결과다(§5-C). 목록(list)이 아니라 **개수(count)만** — 화면에 숫자만 필요하니까.

---

## 4. 공통 메커니즘

### 4-1. 위임 집계 패턴 — 재구현 0, 호출만

home과 settings는 **새 쿼리를 쓰지 않는다.** 이미 검증된 다른 도메인의 서비스/repo를 호출해 결과를 묶을 뿐이다. service 파일 docstring이 이 의도를 못박는다.

```python
# app/domain/home/service.py:1  (파일 docstring)
"""홈 페이지 진입 1호출 overview.
기존 도메인 service (account / transaction / stats) 를 합치는 얇은 집계 레이어.
재구현하지 않고 호출 위임만 한다."""
```

| 도메인 | 무엇을 위임하나 | 부르는 대상 |
|---|---|---|
| **home** | 통장 목록 | `account_service.list_accounts` (03) |
| | 최근 거래 10건 | `transaction_service.list_transactions` (04, 빈 필터 + limit=10) |
| | 이번 달 통계 | `stats_service.get_monthly_stats` (아래 §4-2) |
| **settings** | 도메인별 개수 | 각 repo의 `count_search` / `count` / `count_active_by_household_id` |

> **왜 이렇게?** 잔액 계산·커서 페이징·카테고리 집계는 각 도메인이 이미 "정본"으로 갖고 있다(03·04·stats). home이 그걸 다시 짜면 **로직이 두 벌**이 되어 어긋난다. 그래서 home은 오케스트레이션만 하고 계산은 원 도메인에 맡긴다 — `total_balance`조차 `sum(a.balance for a in accounts)` 한 줄로, 잔액 공식 자체는 03을 신뢰한다(home/service.py:40).

### 4-2. stats 3단 집계 — 타입 합 + 카테고리 합 + 비율

stats의 본체 `get_monthly_stats`(stats/service.py:15)는 **transaction repo 쿼리 2개**로 뼈대를 세운다. 04가 `(→08 stats)`로 넘긴 그 집계다.

**① 타입별 합 — 카드 상단 숫자 (income / expense / transfer)**
```python
# app/domain/transaction/repository.py:395  sum_by_type_for_month
select(Transaction.tx_type, func.coalesce(func.sum(Transaction.amount), 0))
  .where(household_id 일치 & extract(year/month) & data_stat_cd == ACTIVE)
  .group_by(Transaction.tx_type)
# 결과 매핑:
#   INCOME              → income
#   EXPENSE + FIXED_EXPENSE → expense   (★ 둘을 지출로 합산, §4-4)
#   TRANSFER            → transfer
```

**② 카테고리별 합 — 차트/리스트 (by_category)**
```python
# app/domain/transaction/repository.py:343  sum_by_category_for_month
select(Transaction.category_id, func.coalesce(func.sum(Transaction.amount), 0))
  .where(household_id & year/month & category_id IS NOT NULL & data_stat_cd == ACTIVE)
  .group_by(Transaction.category_id)
# TRANSFER 는 category_id 가 없어 자연 제외됨
```

**③ 비율(ratio) 정규화 — 같은 kind 내 max 대비**
```python
# app/domain/stats/service.py:31
kind_max = {True: 0, False: 0}                 # True=수입, False=지출 각각의 최대 금액
for cat_id, amount in category_sums:
    if amount <= 0 or cat_id not in cat_map: continue   # 0/음수·미조회 카테고리 skip
    is_income = cat.kind == CategoryKind.INCOME
    kind_max[is_income] = max(kind_max[is_income], amount)
...
ratio = amount / kind_max[is_income] if kind_max[is_income] > 0 else 0.00
items.sort(key=lambda x: x.amount, reverse=True)         # 금액 큰 순
```
> **`ratio`는 "전체 대비 점유율"이 아니다.** 같은 kind 안에서 **1등 카테고리를 1.00으로 놓은 상대값**이다 — 지출 1등이 30만원이면 15만원 카테고리는 0.50. 차트 막대 길이를 "가장 큰 항목 기준"으로 그리기 위한 값이라, 수입과 지출은 **각자 다른 기준(max)**으로 정규화된다. 파이차트 % 가 필요하면 프론트가 `amount` 합으로 따로 구해야 한다.

### 4-3. 삭제된 카테고리 처리 — `find_by_ids`엔 필터가 없다

카테고리를 soft-delete 해도 그 카테고리로 찍힌 **과거 거래의 금액은 원장에 남아야** 한다(04 원장 불변식). stats는 이걸 조회 방식으로 보장한다.

```python
# app/domain/stats/service.py:25
cat_ids = [cat_id for cat_id, _ in category_sums]   # 이번 달 거래에 등장한 카테고리 id
categories = await cat_repo.find_by_ids(cat_ids)    # ★ find_by_ids 는 data_stat 필터 없음
cat_map = {c.id: c for c in categories}
```
> 주석 그대로: *"find_by_ids 는 필터가 없어 삭제된 카테고리도 포함된다. 삭제된 카테고리의 기존 거래가 by_category 에서 누락되지 않도록."* 만약 "활성 카테고리만" 조회하는 함수를 썼다면, 지운 카테고리의 지출이 **집계에서 통째로 사라져** 월 합계가 안 맞았을 것이다. `if cat_id not in cat_map: continue`가 걸러내는 건 **정말 존재조차 안 하는(하드 삭제)** id뿐 — soft-delete는 통과시킨다.

### 4-4. `FIXED_EXPENSE`는 지출로 합산

거래 타입(04)에는 일반 `EXPENSE`와 고정지출에서 파생된 `FIXED_EXPENSE`가 따로 있다(05). 통계에서는 **둘 다 "지출"** 이다.

```python
# transaction/repository.py:423  sum_by_type_for_month 결과 매핑
elif tx_type in (TxType.EXPENSE, TxType.FIXED_EXPENSE):
    sums["expense"] += Decimal(total)      # ★ 두 타입을 하나의 expense 로 누적
```
> `monthly_expense` = 일반 지출 + 고정지출 파생 거래. 사용자 입장에선 "이번 달 나간 돈"에 관리비·통신비(고정지출) 도 당연히 포함돼야 하니까. `+=` 인 이유가 이것 — 두 tx_type row를 한 칸에 더한다. (income·transfer는 단일 타입이라 `=` 대입.)

---

## 5. 엔드포인트별 풀 트레이스 — GET 3개

셋 다 라우터가 등록돼 있고(main.py:70·71·73), 각각 **읽기 전용 GET 1개**뿐이다. `CurrentHousehold`(→02 멤버십 가드)가 공통 진입 조건.

### A — `GET /home/overview` (홈 대시보드 1호출)

```
요청  GET /api/home/overview?year=&month=   + Bearer + X-Household-Id
      (year/month 생략 가능 — 생략 시 KST 현재)
─[1] 의존성·검증   home/router.py:13  get_overview
      household: CurrentHousehold (→02)
      year/month: Query(ge/le 범위검증) — 둘 다 Optional
─[2] 서비스        home/service.py:26  get_home_overview
      (a) year/month 없으면 → _today_kst() (Asia/Seoul 기준 올해·이번달)   service.py:58
      (b) account_service.list_accounts(db, household)          → 통장 목록 (03)
          total_balance = sum(a.balance for a in accounts)      → Σ 잔액 (§4-1)
      (c) transaction_service.list_transactions(
              db, household, TransactionFilter(), cursor=None, limit=10)  → 최근 10건 (04)
          ※ 빈 필터 + 커서 없음 = 최신순 10건 (RECENT_TX_LIMIT=10, service.py:23)
      (d) stats_service.get_monthly_stats(db, household, year, month)     → §4-2 (그 달 통계)
─[3] 응답 조립     service.py:48  HomeOverviewResponse(
                     total_balance, accounts, recent_transactions=tx_page.items,
                     stats, year, month)
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료 commit
응답  ApiResponse.ok(HomeOverviewResponse)
```
> **홈 화면 = 이 한 번의 호출.** 03(통장)·04(거래)·stats(통계) 세 도메인 서비스를 **순차 호출해 한 응답으로 묶는다.** home은 계산을 안 한다 — `total_balance` 합산 한 줄과 KST 날짜 보정 말고는 전부 위임(§4-1). 06·07이 채운 투자·자산 값은 통장 잔액(INVESTMENT 계좌)과 통계에 이미 녹아 들어와, **여기서 시리즈의 데이터가 한 화면에 모인다.**

### B — `GET /stats/monthly` (월간 카테고리 통계)

```
요청  GET /api/stats/monthly?year=&month=   + Bearer + X-Household-Id
      (year/month 필수 — home과 달리 Query(...) 필수값)
─[1] 의존성·검증   stats/router.py:13  get_monthly_stats
      household: CurrentHousehold (→02) / year·month: 범위검증 필수
─[2] 서비스        stats/service.py:15  get_monthly_stats
      (a) tx_repo.sum_by_type_for_month(household.id, year, month)      → §4-2 ① 타입 합
      (b) tx_repo.sum_by_category_for_month(household.id, year, month)  → §4-2 ② 카테고리 합
      (c) cat_repo.find_by_ids(등장 카테고리 id들)                       → §4-3 삭제분 포함
      (d) valid_rows 걸러내며 kind_max 계산 → CategoryStatsItem 리스트   → §4-2 ③ ratio
      (e) items.sort(amount desc)                                       → 금액 큰 순
─[3] 응답 조립     service.py:57  MonthlyStatsResponse(
                     year, month, monthly_income/expense/transfer, by_category=items)
─[4] 트랜잭션 종료  get_db — 조회뿐
응답  ApiResponse.ok(MonthlyStatsResponse)
```
> **home도 이 함수를 부른다**(§5-A d) — stats.get_monthly_stats는 **stats 라우터와 home 서비스 양쪽의 정본**이다. 04의 월간 요약(monthly-summary)도 이 stats를 `(→08 stats)`로 위임했다. 한 곳(§4-2)에 집계 로직을 두고 세 소비처가 공유하는 구조.

### C — `GET /settings/overview` (설정 화면 카운트)

```
요청  GET /api/settings/overview   + Bearer + X-Household-Id   (파라미터 없음)
─[1] 의존성·검증   settings/router.py:13  get_overview / household: CurrentHousehold
─[2] 서비스        settings/service.py:17  get_settings_overview
      SELECT COUNT(*) 을 도메인마다 한 번씩 — 5번:
        AccountRepository.count_search(household.id)              → 통장 수 (03)
        CategoryRepository.count_search(household.id)             → 카테고리 수 (04)
        FixedRepository.count_search(household.id)                → 고정지출 수 (05)
        TransactionRepository.count(household.id, TransactionFilter())  → 거래 수 (04)
        PortfolioItemRepository.count_active_by_household_id(household.id) → 보유종목 수 (06)
─[3] 응답 조립     service.py:30  SettingsOverviewResponse(각 count 5개)
─[4] 트랜잭션 종료  get_db — 조회뿐
응답  ApiResponse.ok(SettingsOverviewResponse)
```
> **list가 아니라 count.** 설정 화면엔 목록이 아니라 "몇 개"라는 숫자만 필요하니 `COUNT(*)` 5방으로 끝낸다(service.py:2 docstring: *"list 호출이 아니라 SELECT COUNT(*) 5번"*). 각 count 함수는 그 도메인이 이미 검색용으로 갖고 있던 것(`count_search` 등)을 재사용 — 여기서도 위임 패턴(§4-1).

---

## 6. 데이터 흐름 (도메인 큰 그림)

```
        [앞 문서들이 쌓은 데이터]                    [이 문서 — 화면으로 조립]

  03 accounts ─ 잔액                    GET /home/overview
  04 transactions ─ 원장                    │ CurrentHousehold
  05 fixed / 06 portfolio / 07 wealth       ├─▶ account_service.list_accounts ──── 통장+총자산
        │                                    ├─▶ transaction_service.list (limit 10) ─ 최근거래
        │  (전부 조회만, 쓰기 X)              └─▶ stats_service.get_monthly_stats ─┐
        │                                                                          │
        ▼                                  GET /stats/monthly ────────────────────┤ (공유)
  ┌───────────────────────────┐               │                                    │
  │ sum_by_type_for_month     │◀──────────────┤ 타입 합(income/expense/transfer)   │
  │ sum_by_category_for_month │◀──────────────┤ 카테고리 합 → ratio 정규화(§4-2)   │
  └───────────────────────────┘               │ + find_by_ids(삭제 카테고리 포함)  │
                                               ▼                                    │
                                    MonthlyStatsResponse ◀──────────────────────────┘
                                               │ (home 응답에 stats 로 임베드)
                                               ▼
                                    HomeOverviewResponse

  GET /settings/overview ─▶ count × 5 (account/category/fixed/tx/portfolio) ─▶ SettingsOverviewResponse
```

앞 일곱 도메인이 **쓰기(write)로 쌓은** 데이터를, 이 셋이 **읽기(read)로 조립**해 화면에 뿌린다. 쓰는 주체와 읽는 주체가 완전히 분리 — 그래서 이 셋은 테이블이 필요 없다.

---

## 7. 이 문서에서 꼭 기억할 규칙

1. **home·stats·settings 셋 다 테이블이 없다.** `model.py`가 아예 없는 순수 조회/집계 도메인(07 wealth와 같은 부류). 저장하지 않고 앞 도메인 데이터를 읽어 조립만 한다.
2. **home은 재구현 0 — 위임 집계.** account·transaction·stats 서비스를 순차 호출해 한 응답(`HomeOverviewResponse`)으로 묶는 얇은 레이어. `total_balance` 합산과 KST 날짜 보정 말곤 계산이 없다(§4-1).
3. **stats 3단 집계** — `sum_by_type`(카드 숫자) + `sum_by_category`(차트) + `ratio`(같은 kind 내 max 대비 상대값, 전체 점유율 아님)(§4-2). stats.get_monthly_stats는 stats 라우터·home 서비스·04 요약의 **공유 정본**.
4. **삭제된 카테고리의 과거 거래도 집계에 남는다.** `find_by_ids`가 필터 없이 조회해 soft-delete 카테고리를 포함 — 월 합계가 어긋나지 않게(§4-3). 원장(04) 불변식의 통계판.
5. **`FIXED_EXPENSE`는 지출로 합산.** `monthly_expense = EXPENSE + FIXED_EXPENSE` — 관리비·통신비 같은 고정지출도 "이번 달 나간 돈"이니까(§4-4).
6. **settings는 list가 아니라 count.** 화면에 숫자만 필요해 `COUNT(*)` 5방(account/category/fixed/tx/portfolio). 각 도메인의 기존 count 함수 재사용(§5-C).
7. **이 셋은 시리즈의 소비 끝단.** 02~07이 만든 모든 데이터가 home 대시보드 한 화면에 모이며 산책이 닫힌다.

---

## 시리즈를 닫으며

`00`(전체 그림) → `01`(core 인프라) 위에, 데이터를 **쌓는 도메인**(02 인증·세대 → 03 계좌 → 04 거래 → 05 고정·박제 → 06 투자 → 07 시세·자산)을 의존성 순으로 올렸고, 마지막 `08`이 그 전부를 **읽어 화면으로 조립**하며 끝난다. 요청 하나가 `router → service → repository → model`을 어떻게 지나는지, 계좌 잔액이 왜 계산값인지, 박제가 어디서 소비되는지 — 한 줄기로 따라왔다면 이 레포는 더 이상 낯설지 않다. 코드를 열고, 여기서 짚은 `file:line`부터 직접 밟아보면 된다.
