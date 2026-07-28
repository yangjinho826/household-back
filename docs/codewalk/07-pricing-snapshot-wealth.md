
# 07. pricing · wealth — "환율이 시세를 KRW로 채우고, wealth는 박제를 모아 그림을 그린다"

> 06에서 종목 `current_price`는 "항상 KRW", USD 종목은 "환산해서 저장 — 환율/시세 인프라는 07"이라고 넘겼다(06 §5 lookup·refresh, 규칙6). 그 인프라가 여기다. 이 문서의 백미 셋 — ① **환율·시세는 라우터가 없는 내부 도메인** — 사람이 호출하는 API가 아니라 **스케줄러가 돌리는 배치**다. ② **환율 잡(09:00) → 미장 시세 잡(09:10)** 순서가 스케줄 시각에 박혀 있다 — USD 종목을 KRW로 환산하려면 환율이 먼저 있어야 한다. ③ **wealth는 자체 테이블이 하나도 없다** — 05의 계좌 박제(AccountSnapshot)와 06의 종목 박제(PortfolioValueHistory)를 끌어다 자산배분 추이를 **재구성**한다. 시리즈의 결산점이다.

> **이 문서 읽는 법:** 세 도메인을 한 문서로 묶었다. exchange_rate·market_price는 **라우터가 없어** 엔드포인트 트레이스 대신 "배치 진입점(잡)" 트레이스로 본다(§5-A·B). wealth만 진짜 엔드포인트가 1개(§5-C). §4(공통 메커니즘)에 야후 연동·환율→시세 순서 의존·스케줄러·자산군 분류를 한 번 정리하고, §5는 거기를 `→ §4-x`로 참조한다.

---

## 1. 이 도메인 한마디

**투자자산을 "지금 얼마"로 환산하고, 그걸 모아 "자산이 어떻게 배분돼 있나"를 그린다.** 환율(exchange_rate)이 USD/KRW 한 줄을 매일 갱신하고, 시세(market_price)가 야후에서 종목 현재가를 받아 — USD 종목은 환율을 곱해 KRW로 — `portfolio_items.current_price`를 채운다. 둘 다 **사람이 부르는 API가 아니라 스케줄러 배치**다. wealth는 그 위에서, 계좌·종목·현금을 자산군(`AssetClass`)으로 묶어 **현재 배분 파이 + 월별 배분 추이**를 만든다 — 자체 테이블 없이 05·06의 박제를 재구성해서.

---

## 2. 들어가기 전 (개념 콕)

| 개념 | 한마디 |
|---|---|
| **내부 도메인 (라우터 미등록)** | exchange_rate·market_price는 `include_router`에 없다(§3). HTTP 진입점이 없는 **배치 전용** 도메인 — 진입점은 스케줄 잡이거나, 06이 위임하는 service 호출뿐. |
| **야후 chart quote** | 시세든 환율이든 같은 야후 endpoint(`/v8/finance/chart/{symbol}`) 한 곳에서 가격을 뽑는다(§4-1). 환율 심볼은 `KRW=X`, 종목은 `code+suffix`. |
| **환율 선행 의존** | USD 종목을 KRW로 환산하려면 `currency_rates`에 USD/KRW가 먼저 있어야 한다. 그래서 환율 잡(09:00) → 미장 잡(09:10) 순서가 **스케줄 시각에 박혀 있다**(§4-2). |
| **advisory lock 멱등 잡** | 모든 잡은 `run_locked_job`으로 감싼다 — 자체 세션 + PostgreSQL transaction-scoped advisory lock. 다중 워커가 같은 잡에 동시 진입해도 1개만 통과(§4-3). |
| **자산군 (AssetClass)** | 모든 자산을 INVESTMENT / CASH / REAL_ESTATE / PENSION / COMMODITY / SAVINGS 슬라이스로 분류하는 축(§4-4). 배분 파이/추이의 칸. |
| **박제 소비처 (결산점)** | wealth는 박제를 **만들지 않고 읽기만** 한다. 05의 `account_snapshots`·06의 `portfolio_value_history`를 끌어다 추이를 재구성 — 시리즈에서 박제가 최종 소비되는 곳. |

---

## 3. 데이터 모델 — 자체 테이블은 단 하나

세 도메인 중 테이블을 가진 건 **exchange_rate 하나뿐.** 나머지 둘이 테이블 없이 동작하는 게 이 문서의 핵심 구조다.

### 3-1. `currency_rates` — 환율 (exchange_rate의 유일한 테이블)

```python
# app/domain/exchange_rate/model.py:9
class CurrencyRate(BaseEntity):
    __tablename__ = "currency_rates"
    __table_args__ = (UniqueConstraint("base_currency", "quote_currency",
                                       name="uq_currency_rates_pair"),)  # 쌍당 1 row
    base_currency:  Mapped[str]      # CHAR(3) — "USD"
    quote_currency: Mapped[str]      # CHAR(3) — "KRW"
    rate:           Mapped[Decimal]  # Numeric(15,4) — 1 USD = ? KRW
```

> **(base, quote) 쌍당 정확히 1행, 매번 덮어쓴다.** UNIQUE 제약이 그걸 강제한다. 환율 이력을 쌓는 게 아니라 "지금 환율" 한 줄만 유지 — 마지막 갱신 시각은 `BaseEntity.last_mdfcn_dt`(onupdate)가 자동으로 찍는다(model.py:11 주석). 통화는 `CurrencyCode` enum으로 USD/KRW 둘뿐(enum.py:4).

### 3-2. market_price — **테이블 없음** (portfolio_items를 직접 갱신)

market_price 도메인 폴더에는 `service.py`·`yahoo_client.py`뿐 — `model.py`가 없다. 시세를 따로 저장하지 않고, **06의 `portfolio_items.current_price`를 직접 덮어쓴다**(service.py 파일 docstring). 왜 별도 테이블을 안 두나:

- 시세는 "지금 값"만 필요하다 — 이력은 06의 월별 박제(`portfolio_value_history`)가 이미 맡는다(06 §3-3).
- `current_price`는 **항상 KRW** — USD 종목도 환산해서 넣으므로, `qty * current_price` 합산이 단일 통화에서 의미를 가진다(06 규칙6과 같은 invariant).

### 3-3. wealth — **테이블 없음** (복합 조회 전용 도메인)

wealth 폴더에는 `service.py`·`router.py`·`schema.py`뿐 — 역시 `model.py`가 없다. **자기 데이터를 1바이트도 저장하지 않는다.** 하는 일은 오직 — 05의 `account_snapshots` + 06의 `portfolio_value_history` + `accounts`를 읽어 자산군 배분으로 **재구성**하는 것. 응답 스키마만 있다(schema.py):

```python
# app/domain/wealth/schema.py
AssetClassSlice      # 배분 파이 1칸 — asset_class / valuation / ratio(%)
AllocationTrendPoint # 월별 추이 1포인트 — snapshot_date / slices[]
AllocationResponse   # current_allocation(현재) + allocation_trend(월별)
WealthOverviewResponse # total_balance / accounts[] / yearly_snapshots / allocation
```

### 자산군을 나누는 enum — `AssetClass`

```python
# app/domain/portfolio/enum.py:11  (06 §3에서 "07에서 다룬다"고 넘긴 enum)
class AssetClass(StrEnum):  INVESTMENT / COMMODITY / CASH / REAL_ESTATE / PENSION / SAVINGS ...
```

> `AssetClass`는 enum 정의 자체는 portfolio 도메인에 있지만(종목과 한 파일), **실제로 쓰는 곳은 wealth**다. 06이 "자산배분 축은 07 wealth에서"라고 넘긴 게 이 enum의 소비처다.

---

## 4. 공통 메커니즘

### 4-1. 야후 연동 — `fetch_chart_quote` 한 곳, 재시도 1회

시세든 환율이든 **같은 함수**로 가격을 받는다. 야후 chart endpoint가 둘 다 커버하기 때문.

```python
# app/domain/market_price/yahoo_client.py:41  fetch_chart_quote(symbol)
url = f"{_BASE_URL}/{symbol}"                       # /v8/finance/chart/{symbol}
for attempt in range(2):                            # 최대 2회 (원샷 + 재시도 1회)
    try: ... response.raise_for_status(); payload = response.json()
    except httpx.HTTPError as e:
        if attempt == 0 and _is_retryable(e):       # 일시 오류만 재시도
            await asyncio.sleep(_RETRY_BACKOFF_SEC); continue   # 1.0s 후
        return None                                 # 영구 오류 / 2번째 실패 → None
    price = meta.get("regularMarketPrice")          # meta에서 가격
    return ChartQuote(price=Decimal(str(price)), name=longName or shortName)
```

- **재시도 대상은 일시 오류만** — `_is_retryable`(yahoo_client.py:34): 408/425/429/5xx 또는 timeout/connect/read 오류. 404 같은 영구 오류는 **즉시 None**(재시도 안 함).
- **None = "이 심볼은 못 받았다"** — 호출자가 skip을 결정한다. 잡을 죽이지 않는다.
- `ChartQuote`는 `price` + `name`(longName/shortName 없으면 None). 06의 `lookup`(폼 자동채움)은 name을 쓰고, 시세 갱신은 price만 쓴다.

> 환율 심볼 `KRW=X`도, 종목 심볼 `005930.KS`도 이 함수 하나를 통과한다. 야후 심볼 생성은 06 §3의 `Market.yahoo_suffix`를 쓰는 `build_yahoo_symbol`(portfolio/yahoo.py:17) — KOSPI→`.KS`, 미국장→suffix 없음.

### 4-2. 환율 → 시세, 순서가 스케줄에 박혀 있다

**USD 종목을 KRW로 환산하려면 환율이 DB에 먼저 있어야 한다.** 이 의존이 두 층위에 박제돼 있다.

**① 코드 레벨 — 환율 없으면 USD 시장을 통째로 제외**
```python
# app/domain/market_price/service.py:61  refresh()
needs_fx = any(m in _USD_MARKETS for m in markets)   # NASDAQ/NYSE 포함?
if needs_fx:
    latest = await CurrencyRateRepository(session).find_by_pair(USD, KRW)
    if latest is None:                               # 환율 잡이 아직 안 돌았으면
        markets = [m for m in markets if m not in _USD_MARKETS]   # USD 시장 제외
        if not markets: return RefreshResult(0, 0, 0)            # 다 빠지면 빈 결과
    else:
        fx_rate = latest.rate                        # 환율 확보 → 환산에 사용
```

**② 스케줄 레벨 — 시각 자체가 순서를 보장**
| 잡 | 시각 (KST) | 요일 | 의미 |
|---|---|---|---|
| `refresh_usd_krw_job` | **09:00** | 월~금 | 환율 먼저 |
| `refresh_us_prices_job` | **09:10** | 화~토 | 미장 close + 환율 갱신 **후** |

> 09:00 환율 → 09:10 미장. 10분 간격은 우연이 아니라 **"환율이 먼저 채워진 뒤 USD 종목을 환산한다"**는 의존을 시각으로 표현한 것(scheduler.py:58 주석). 미장은 한국시각 새벽에 close하므로 09:10이면 전날 종가가 안정적으로 잡힌다. 화~토인 이유 — 미국 월요일장 = 한국 화요일 새벽.

**환산은 `_fetch_one`에서 종목별로**
```python
# market_price/service.py:128  _fetch_one(code, market, fx_rate)
quote = await fetch_chart_quote(build_yahoo_symbol(market, code))
if quote is None or quote.price <= 0: return None
price = quote.price
if market in _USD_MARKETS and fx_rate is not None:
    price = price * fx_rate                          # ★ USD → KRW 환산
return price.quantize(Decimal("0.01"), ROUND_HALF_UP)  # 원 단위 KRW로 박제
```

### 4-3. 스케줄러 5잡 + advisory lock (이 문서는 시세·환율 3잡이 정본)

스케줄러에는 잡이 5개 등록된다(scheduler.py:55 `register_jobs`). 이 문서가 **정본으로 다루는 건 환율·시세 3잡**, 나머지 2잡은 다른 문서 소관이다.

| 잡 | 시각(KST) | 정본 문서 |
|---|---|---|
| `refresh_usd_krw` | 09:00 월~금 | **07 (여기)** |
| `refresh_us_prices` | 09:10 화~토 | **07 (여기)** |
| `refresh_kr_prices` | 16:10 월~금 (국장 close 직후) | **07 (여기)** |
| `cleanup_idempotency` | 매시 :00 | core/idempotency (→ 01) |
| `create_monthly_snapshots` | 매월 1일 00:30 | account_snapshot (→ 05) |

**모든 잡은 `run_locked_job`으로 감싼다 — 멱등성의 핵심.**
```python
# app/core/scheduler.py:32  run_locked_job(job_name, fn)
async with async_session() as session:              # ① 요청 DI와 분리된 자체 세션
    async with session.begin():                     # ② 명시 트랜잭션 (lock 수명 범위)
        if not await try_advisory_lock(session, job_name):   # ③ pg_try_advisory_xact_lock
            return                                  #    실패 = 다른 워커가 잡음 → 조용히 skip
        try: await fn(session)                       # ④ 실제 작업
        except Exception: logger.exception(...); raise   # ⑤ 로그 + 재발생(다음 trigger 대기)
```
> advisory lock은 **transaction-scoped** — 트랜잭션 끝나면 자동 해제(scheduler.py:19). 다중 인스턴스/워커가 같은 시각에 같은 잡을 띄워도 1개만 통과. 05의 월간 박제 잡도 같은 `run_locked_job`을 쓴다 — **잡 멱등 메커니즘은 공유, 여기선 시세/환율 잡 관점으로만 본다**(잡 자체 배선은 05·01이 정본).

### 4-4. 자산군 분류 — 현재는 직접, 과거는 역산

wealth가 자산을 `AssetClass` 슬라이스로 나누는 규칙. 핵심은 **INVESTMENT 통장의 현금을 어떻게 구하느냐**가 현재/과거에서 다르다는 점.

**전용계좌 매핑 (수동자산 4종)**
```python
# app/domain/wealth/service.py:39
_ASSET_CLASS_BY_TYPE = {
    AccountType.REAL_ESTATE:   AssetClass.REAL_ESTATE,
    AccountType.PENSION:       AssetClass.PENSION,
    AccountType.COMMODITY:     AssetClass.COMMODITY,
    AccountType.SAVINGS_ASSET: AssetClass.SAVINGS,    # ← 부동산·연금·금 + 저축자산 = 4종
}
```

**① 현재 배분 — `_build_allocation`(service.py:144): cash 필드를 직접 쓴다**
```python
for a in accounts:
    if a.account_type == INVESTMENT:  slices[CASH] += a.cash      # ★ 계좌의 cash 필드 직접
    elif a.account_type in _ASSET_CLASS_BY_TYPE: slices[매핑] += a.balance
    else:                             slices[CASH] += a.balance   # 일반계좌 = 전액 현금
for item in items:
    slices[INVESTMENT] += item.quantity * item.current_price     # 종목은 전부 INVESTMENT
```

**② 월별 추이 — `_add_snapshot_to_month`(service.py:170): balance에서 역산한다**
```python
# 박제(AccountSnapshot)에는 cash 필드가 없다 → balance − 그달 종목평가액으로 역산
if account_type == INVESTMENT:  month[CASH] += balance - pvh_valuation   # ★ 역산
elif account_type in _ASSET_CLASS_BY_TYPE: month[매핑] += balance
else:                           month[CASH] += balance
```

> **왜 다른가?** 현재 시점 계좌(`AccountResponse`)에는 `cash`가 계산돼 있어 바로 쓴다. 하지만 **과거 박제(`AccountSnapshot`)에는 balance만 박제돼 cash가 없다** — 그래서 그달 종목 평가액(`portfolio_value_history` 합)을 balance에서 빼서 현금을 역산한다. 같은 INVESTMENT 통장인데 06 §4-4의 `balance = cash + valuation` 공식을 거꾸로 푸는 셈. 종목 평가액 자체는 양쪽 다 INVESTMENT 슬라이스로 따로 합산하므로, 통장에서는 현금만 떼어낸다.

---

## 5. 진입점별 트레이스 — 잡 2개 + 엔드포인트 1개

exchange_rate·market_price는 **라우터가 없다**(§3) — `main.py`의 `include_router` 목록에 wealth만 있고 둘은 없다(main.py:72). 그래서 HTTP 트레이스 대신 **배치 진입점(잡)** 으로 따라간다.

### A — 환율 배치 진입점 `refresh_usd_krw_job`

```
진입  스케줄러 09:00 KST (월~금)   core/jobs.py:15  refresh_usd_krw_job
─[1] 잡 래퍼      run_locked_job("refresh_usd_krw", exchange_rate_service.refresh)  → §4-3
                  자체 세션 + advisory lock + 트랜잭션
─[2] 서비스       exchange_rate/service.py:18  refresh(session)
      fetch_chart_quote("KRW=X")              → §4-1 (None이면 ERROR 로그만, 잡 안 죽음)
      rate = quote.price.quantize(0.0001)
      find_by_pair(USD, KRW)
        ├ 있으면 → existing.rate = rate; flush  (dirty checking UPDATE)
        └ 없으면 → save(CurrencyRate(USD, KRW, rate))  (최초 1회 INSERT)
─[3] 트랜잭션 종료  run_locked_job 의 session.begin() 블록 — 정상 종료 시 commit
결과  currency_rates 의 USD/KRW 한 줄 갱신 (이력 X, 덮어쓰기)
```
> **upsert 한 줄.** 처음엔 INSERT, 이후로는 영원히 UPDATE. fetch 실패해도 `return`만 — 다음 스케줄(내일 09:00)에 재시도. 이 한 줄이 §4-2의 미장 잡이 의존하는 바로 그 환율이다.

### B — 시세 배치 진입점 `refresh_kr_prices_job` / `refresh_us_prices_job`

```
진입  국장: 16:10 월~금   core/jobs.py:20  refresh_kr_prices_job  → [KOSPI, KOSDAQ]
      미장: 09:10 화~토   core/jobs.py:31  refresh_us_prices_job  → [NASDAQ, NYSE]
─[1] 잡 래퍼      run_locked_job(..., _run)  → §4-3   (markets 만 다르고 본체는 공유)
─[2] 서비스       market_price/service.py:42  refresh(session, markets, household_id=None)
      (1) USD 시장 포함 시 환율 확보 — 없으면 USD 시장 제외       → §4-2 ①
      (2) find_active_distinct_code_market_by_markets  → (code, market) DISTINCT
          ※ household_id=None(스케줄) = 전 가계부 / 있으면(수동) 그 가계부만
      (3) 청크 10개씩 asyncio.gather + 청크 사이 0.2s sleep      (야후 rate-limit 회피)
            └ _fetch_one: 야후 호출 → USD면 환율 곱 → quantize(0.01)  → §4-2
            └ None/예외는 per-item skip (잡 안 죽음)
      (4) bulk_update_current_price_by_code_market(prices)  → 매칭 전 가계부 row 일괄 UPDATE
─[3] 트랜잭션 종료  commit
결과  RefreshResult(fetched, skipped, updated_rows)  — 로그로 관측
```
> **가격은 시장 공통**이라, 한 종목 가격을 받으면 그 (code, market)을 보유한 **모든 가계부 row를 한 번에** 갱신한다(DISTINCT로 중복 호출 제거 + bulk update). 06의 `POST /portfolio/refresh-prices`(수동 새로고침)도 이 `refresh`를 `household_id` 채워서 호출 — **06↔07의 접점**(06 §5 그룹E). 정본은 여기, 06은 "위임한다"까지만.

### C — wealth 엔드포인트 `GET /wealth/overview` (유일한 HTTP 진입점)

```
요청  GET /api/wealth/overview?fromDate=&toDate=   + Bearer + X-Household-Id
─[1] 의존성·검증   wealth/router.py:16  get_overview
      household: CurrentHousehold (→ 02 멤버십 가드) + SnapshotYearlyQuery(from/to optional)
─[2] 서비스        wealth/service.py:47  get_wealth_overview
      (a) account_service.list_accounts → total_balance = Σ balance
      (b) PortfolioItemRepository.find_active_by_household_id → 현재 보유종목
      (c) _build_allocation(accounts, items)  → 현재 배분 파이          → §4-4 ①
      (d) resolve_snapshot_range(from, to)  → to=지난달, from=to−11개월 (그달 1일)
          ※ account_snapshot 의 연간추이와 같은 축 공유 (account_snapshot/service.py:90)
      (e) AccountSnapshotRepository.find_by_household_and_range      ← 05 박제 회수
          PortfolioValueHistoryRepository.find_by_household_and_range ← 06 박제 회수
          AccountRepository.find_by_ids(snapshot 계좌들)
      (f) build_allocation_trend(snapshots, histories, accounts)  → 월별 배분 추이  → §4-4 ②
      (g) account_snapshot_service.get_yearly_snapshots  → 연간 income/expense (→ 05)
─[3] 응답 조립     service.py:82  WealthOverviewResponse(total_balance, accounts,
                                  yearly_snapshots, allocation{current + trend})
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(WealthOverviewResponse)
```

**(f) `build_allocation_trend`(service.py:90) 속을 한 번 더**
```python
for h in portfolio_histories:                        # 06 종목 박제
    pvh_by_account[(date, account_id)] += h.valuation # 계좌별 종목평가 (INVESTMENT cash 역산용)
    trend[date][INVESTMENT] += h.valuation            # 종목은 전부 INVESTMENT 슬라이스
for s in account_snapshots:                           # 05 계좌 박제
    _add_snapshot_to_month(trend[date], 계좌타입, s.balance,
                           pvh_by_account[(date, s.account_id)])   # → §4-4 ②
# 월별로 _slices_to_list: 0값 제외 + ratio(%) 채움 + valuation desc 정렬
```
> 여기가 **시리즈의 결산점**. 05가 박제한 계좌 잔액 + 06이 박제한 종목 평가액이, 이 한 함수에서 월별 자산군 슬라이스로 합쳐져 추이 차트가 된다. wealth는 아무것도 저장하지 않고 **읽어서 재구성만** 한다.

---

## 6. 데이터 흐름 (도메인 큰 그림)

```
[배치 — 사람 없음]                          [조회 — 프론트]
 스케줄러 (KST)                              GET /api/wealth/overview
   │                                              │ CurrentHousehold (멤버십 가드)
   ├ 09:00 환율잡 ──▶ fetch_chart_quote("KRW=X")  │
   │                    └▶ currency_rates upsert   │
   │                          (USD/KRW 한 줄)      │
   │                            │ 선행 의존         │
   ├ 09:10 미장잡 ──▶ refresh([NASDAQ,NYSE])       │
   │                    환율 곱해 KRW 환산          │
   ├ 16:10 국장잡 ──▶ refresh([KOSPI,KOSDAQ])      │
   │                    └▶ portfolio_items          │
   │                        .current_price (KRW)    │
   │                            │                   │
   └ (매월1일 박제잡 → 05·06)                       │
        account_snapshots ─┐  portfolio_value_history ─┐
                           ▼                           ▼
                    wealth.get_wealth_overview ─── 박제 회수 + 재구성
                           │
              ┌────────────┴────────────┐
        현재 배분(cash 직접)      월별 추이(balance 역산)
          §4-4 ①                   §4-4 ②  ← 결산점
                           │
                  WealthOverviewResponse
                (total / accounts / yearly / allocation)
```

배치가 `current_price`를 KRW로 채워두면(왼쪽), wealth가 그 값과 박제들을 끌어다 자산배분을 그린다(오른쪽). **쓰는 쪽(배치)과 읽는 쪽(wealth)이 시간·주체가 완전히 분리**돼 있다.

---

## 7. 이 문서에서 꼭 기억할 규칙

1. **환율·시세는 라우터 없는 내부 도메인.** `main.py` include_router에 wealth만 있고 둘은 없다 — 진입점은 스케줄 잡 또는 06이 위임하는 service 호출뿐.
2. **환율(09:00) → 미장 시세(09:10) 순서는 의존이다.** USD 종목 KRW 환산에 환율이 선행돼야 해서, 코드(없으면 USD 시장 제외)와 스케줄 시각 양쪽에 박혀 있다(§4-2).
3. **`current_price`는 항상 KRW** — USD 종목은 시세 갱신 시점에 환율을 곱해 박제(06 규칙6의 본체). market_price는 자체 테이블 없이 `portfolio_items`를 직접 갱신.
4. **모든 잡은 advisory lock 멱등** — `run_locked_job`(자체 세션 + transaction-scoped lock). 다중 워커 동시 진입해도 1개만 통과, 실패는 다음 trigger 재시도(§4-3).
5. **야후 연동은 `fetch_chart_quote` 한 곳** — 시세·환율 공용, 일시 오류 1회 재시도, 영구 오류/누락은 None(skip). 잡을 죽이지 않는다.
6. **wealth는 테이블이 없다 = 박제 소비처.** 05의 계좌 박제 + 06의 종목 박제를 읽어 자산군 추이로 재구성 — 시리즈의 결산점.
7. **현금은 현재=직접(`a.cash`), 과거=역산(`balance − 종목평가`).** 박제에 cash 필드가 없어서 06 §4-4 공식을 거꾸로 푼다(§4-4). 수동자산 전용계좌는 4종(부동산·연금·금·저축).

---

## 다음 문서
➡ **`08-home-stats-settings.md`** — 시리즈 마지막. 여러 도메인을 한 화면으로 합치는 **home**(대시보드 집계), 기간/카테고리 통계의 **stats**, 그리고 사용자·가계부 환경설정의 **settings** 를 본다. 06·07이 만든 투자·자산 데이터가 홈 대시보드에서 어떻게 한 번에 소비되는지로 시리즈를 닫는다.
