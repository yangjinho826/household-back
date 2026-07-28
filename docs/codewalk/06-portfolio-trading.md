
# 06. portfolio — 주식 매매, 그리고 "평단은 거래를 다시 돌려 계산한다"

> 03에서 INVESTMENT(투자) 통장의 잔액은 `현금 + 보유종목 평가액`이라고 했다(03 §4-2). 그 **보유종목**이 사는 곳이 여기다. 이 도메인의 백미 셋 — ① **평단(평균단가)을 저장하되, 거래가 바뀌면 전체 거래를 시간순으로 다시 돌려(replay) 재계산**한다, ② **매도 실현손익(realized PnL)을 매도 시점 평단으로 건별 박제**하고 거래 수정 시 같은 replay로 재박제한다, ③ **종목별 월말 평가액을 박제**(PortfolioValueHistory)해 자산 추이 차트를 만든다.

> **이 문서 읽는 법:** 이 도메인은 엔드포인트가 17개로 가장 많다. §4(공통 메커니즘)에 평단 재계산·실현손익 replay·PNL 공식 같은 "여러 API가 공유하는 심장부"를 한 번 깊게 정리했다. §5(엔드포인트별 트레이스)는 17개를 **6그룹**으로 묶어, 그룹마다 대표 1개를 요청→응답까지 따라가고 나머지는 차이점만 짚는다. 공통 로직은 `→ §4-x`로 참조한다.

---

## 1. 이 도메인 한마디

**투자 통장 안의 보유 종목과 그 매매 이력.** 삼성전자 10주, 애플 5주 같은 **보유 종목(PortfolioItem)** 을 등록하고, 매수/매도할 때마다 **거래 이력(PortfolioTransaction)** 을 남긴다. 핵심은 **평단(평균 매입 단가)** 과 **실현손익** — 둘 다 거래 이력을 근거로 계산되고, 거래가 수정되면 다시 계산된다. 매달 평가액을 박제(PortfolioValueHistory)해 "내 투자자산이 어떻게 불었나" 차트를 그린다.

---

## 2. 들어가기 전 (개념 콕)

| 개념 | 한마디 |
|---|---|
| **평단(이동평균)** | 같은 종목을 여러 번 사면 매입가가 섞인다. `(기존수량×기존평단 + 산수량×산가격) / 총수량`. 매도해도 평단은 안 변한다(§4-2). |
| **실현손익(realized PnL)** | 팔아서 **확정된** 손익 = `(매도가 − 매도시점 평단) × 수량`. 안 판 보유분의 평가손익(unrealized)과 구분(§4-3). |
| **replay(거래 재생)** | 거래를 **시간순으로 처음부터 다시 적용**해 현재 상태를 복원하는 기법. 거래 수정/삭제 시 평단·실현손익을 한 번에 바로잡는다(§4-2·4-3). |
| **박제(snapshot)** | 그 시점 값을 고정 저장. 평가액은 매달 변하므로 월말에 떠서 보관(PortfolioValueHistory) → 추이 차트(§4-5). |
| **soft delete vs archive** | 종목 삭제=`data_stat_cd="99"`. 보관=`is_archived=True`. **전량 매도하면 자동 soft delete**(§5 sell). |
| **논리 FK** | `account_id`·`portfolio_item_id` 모두 DB 제약 없는 논리 FK(03과 동일). 소속·소유는 서비스가 `household_id` 비교로 검증. |

---

## 3. 데이터 모델 — 3테이블

투자 도메인은 한 테이블이 아니라 **역할이 다른 3테이블**로 나뉜다.

### 3-1. `portfolio_items` — 보유 종목 (현재 상태)

```python
# app/domain/portfolio/model.py:11
class PortfolioItem(BaseEntity):
    household_id:   Mapped[UUID]     # 소속 가계부 (논리 FK)
    account_id:     Mapped[UUID]     # 소속 INVESTMENT 통장 (논리 FK)
    name:           Mapped[str]      # 종목명 "삼성전자"
    code:           Mapped[str]      # 종목코드 "005930"
    market:         Mapped[str]      # Market enum 값 — "KRX_KOSPI" 등
    quantity:       Mapped[Decimal]  # Numeric(15,4) — 현재 보유 수량
    avg_price:      Mapped[Decimal]  # Numeric(15,2) — 현재 평단 (계산 결과를 저장)
    current_price:  Mapped[Decimal]  # Numeric(15,2) — 현재가 (야후/수동 갱신, 항상 KRW)
    is_archived:    Mapped[bool]     # 보관 여부
```

> **`quantity`·`avg_price`는 저장한다.** 03 통장 잔액은 "저장 안 함(파생)"이었는데, 종목 수량/평단은 **저장값**이다. 다만 진실의 원천은 거래 이력 — 거래가 바뀌면 replay로 다시 계산해 이 컬럼을 **덮어쓴다**(§4-2). 즉 "캐시된 파생값"에 가깝다.

### 3-2. `portfolio_transactions` — 매매 이력 (불변 기록)

```python
# app/domain/portfolio/model.py:31
class PortfolioTransaction(BaseEntity):
    household_id:        Mapped[UUID]
    account_id:          Mapped[UUID]
    portfolio_item_id:   Mapped[UUID|None]  # 어느 종목의 거래인가 (논리 FK, nullable)
    name/code/market:    Mapped[str]        # 거래 시점 종목 정보 스냅샷
    pt_type:             Mapped[str]        # "BUY" / "SELL"
    quantity:            Mapped[Decimal]    # 거래 수량
    price:               Mapped[Decimal]    # 거래 단가 (KRW 박제)
    tx_date:             Mapped[date]       # 거래일
    memo:                Mapped[str|None]
    realized_pnl:        Mapped[Decimal|None]  # ★ SELL만 채워짐 — 매도 실현손익
    realized_cost_basis: Mapped[Decimal|None]  # ★ SELL만 — 매도시점 평단×수량 (원가)
```

> **`realized_pnl`·`realized_cost_basis`는 SELL에만.** 매도 시점 평단을 박제한다(§4-3). model.py:52 주석대로 **R2(리비전2) 이전 구버전 SELL은 NULL** — 매도시점 평단 복원이 불가했던 시절 데이터. 집계 때 `NULL → 0`으로 간주해 합계 왜곡을 막는다(service.py:393).

### 3-3. `portfolio_value_history` — 월별 평가액 박제 (추이용)

```python
# app/domain/portfolio/model.py:60
class PortfolioValueHistory(BaseEntity):
    household_id:      Mapped[UUID]
    account_id:        Mapped[UUID]
    portfolio_item_id: Mapped[UUID]    # 어느 종목
    snapshot_date:     Mapped[date]    # 박제 기준일 (매월 1일)
    quantity:          Mapped[Decimal] # 그 시점 보유 수량
    avg_price:         Mapped[Decimal] # 그 시점 평단
    current_price:     Mapped[Decimal] # 그 시점 현재가
    cost:              Mapped[Decimal] # 그 시점 원가 = qty×avg_price
    valuation:         Mapped[Decimal] # 그 시점 평가액 = qty×current_price
```

> 매달 1일 스케줄러가 종목마다 한 줄씩 떠서 넣는다(§4-5). 종목을 삭제해도 이 행은 **보존**(`delete_portfolio`가 value_history는 안 건드림) — 과거 추이를 잃지 않기 위해.

### 종목을 분류하는 enum 3종

```python
# app/domain/portfolio/enum.py
class PortfolioTxType(StrEnum):  BUY="BUY"  SELL="SELL"          # :4 거래 종류
class Market(StrEnum):  KRX_KOSPI / KRX_KOSDAQ / NASDAQ / NYSE / OTHER  # :28 시장
class AssetClass(StrEnum):  INVESTMENT/COMMODITY/CASH/...        # :11 자산배분 축 (→ 07 wealth)
```

- **`Market`** — 야후 심볼 접미사와 1:1(`yahoo_suffix`, enum.py:42). KRX_KOSPI→`.KS`, KOSDAQ→`.KQ`, 미국장은 빈 문자열. **OTHER**(금·채권 등 야후 미지원)는 `yahoo_suffix` 접근 시 KeyError — "절대 야후 호출 안 함"의 invariant. `country_code`(enum.py:52)로 KR/US 환산 분기.
- **`AssetClass`** — 종목은 전부 INVESTMENT 한 덩어리, 수동자산(부동산/연금/금) 통장은 각자 슬라이스. 자산배분 파이/추이용 → **07 wealth 문서**에서 다룬다.

---

## 4. 공통 메커니즘

이 도메인의 심장. §5 트레이스가 전부 이 절들을 참조한다.

### 4-1. PNL 계산 — `_build_response`

종목 응답을 만들 때마다 평가손익을 계산해 싣는다(DB 컬럼 아님).

```python
# app/domain/portfolio/service.py:659  _build_response
cost        = item.quantity * item.avg_price        # 원가 = 보유수량 × 평단
valuation   = item.quantity * item.current_price    # 평가액 = 보유수량 × 현재가
profit_loss = valuation - cost                       # 평가손익 (미실현)
profit_loss_rate = profit_loss / cost * 100  if cost > 0 else 0   # 수익률 %
```

> 이건 **미실현(unrealized) 손익** — 아직 안 판 보유분의 장부상 손익. 팔아서 **확정**된 실현손익(§4-3)과는 다른 축이다. `current_price`가 야후로 갱신될 때마다 이 값도 자동으로 따라 변한다(저장 안 하니까).

### 4-2. 평단(이동평균) — 매수는 즉시, 수정/삭제는 replay

평단을 바꾸는 경로가 **둘**이다.

**① 매수 — 그 자리에서 가중평균 한 줄**
```python
# app/domain/portfolio/service.py:155  buy()
if item.quantity == 0:
    item.avg_price = req.price                       # 첫 매수면 그냥 매수가
else:
    item.avg_price = (
        item.quantity * item.avg_price + req.quantity * req.price
    ) / (item.quantity + req.quantity)               # 가중평균
item.quantity += req.quantity
```

**② 매도 — 평단 불변, 수량만 차감**
```python
# service.py:245  sell()
remaining = item.quantity - req.quantity   # 평단(avg_price)은 안 건드림
if remaining == 0:
    item.data_stat_cd = DataStatus.DELETED  # ★ 전량매도 = 종목 soft delete
```
> 매도해도 평단이 안 변하는 게 이동평균의 핵심 — "남은 주식의 평균 매입가"는 일부 판다고 달라지지 않는다.

**③ 거래 수정/삭제 — 전체 replay로 재계산 (`_recalc_item_from_transactions`)**
```python
# service.py:749  거래 PUT/DELETE 후 호출
txs = await pt_repo.find_active_by_item_id(item.id)        # 활성 거래 시간순 전부
remaining_qty, remaining_cost = _recompute_realized_pnl(txs)  # replay (§4-3과 공유)
if remaining_qty < 0:
    raise CustomException(ErrorCode.BAD_REQUEST)           # 매도 > 매수면 거부
item.quantity  = remaining_qty
item.avg_price = remaining_cost / remaining_qty if remaining_qty > 0 else 0
item.data_stat_cd = ACTIVE if remaining_qty > 0 else DELETED  # 0이면 소멸, 양수면 부활
```

> **왜 replay인가?** "과거 거래 1건이 수정됐다"면 그 이후 평단·실현손익이 전부 틀어진다. `전체매수합/전체매수량` 같은 단순식은 **매도 후 재매수**를 만나면 평단을 왜곡한다. 그래서 거래를 처음부터 다시 돌려(running_qty/running_cost) 정확히 복원한다. 매수의 즉시 계산(①)은 "마지막에 한 건 추가"의 빠른 경로일 뿐, 진실의 원천은 항상 거래 이력이다.

### 4-3. 실현손익 박제 + 재박제 — `_recompute_realized_pnl`

매도할 때 "이 매도로 얼마 벌었나"를 **그 시점 평단 기준으로 건별 박제**한다.

**매도 즉시 박제 (sell)**
```python
# service.py:218  sell()
realized_cost = item.avg_price * req.quantity                 # 원가 = 매도시점 평단 × 수량
realized_pnl  = (req.sell_price - item.avg_price) * req.quantity  # 손익 = (매도가-평단) × 수량
# → PortfolioTransaction.realized_pnl / realized_cost_basis 에 박제
```

**거래 수정 시 재박제 (replay)**
```python
# service.py:718  _recompute_realized_pnl — 거래를 시간순 재생하며 SELL마다 다시 박제
running_qty, running_cost = 0, 0
for t in txs:                                    # tx_date ASC 정렬된 거래들
    if t.pt_type == BUY:
        running_qty  += t.quantity
        running_cost += t.quantity * t.price
    elif t.pt_type == SELL:
        running_avg = running_cost / running_qty if running_qty > 0 else 0
        t.realized_cost_basis = running_avg * t.quantity      # ★ 그 시점 평단으로 재박제
        t.realized_pnl        = (t.price - running_avg) * t.quantity
        running_cost -= running_avg * t.quantity              # 평단 비율로 원가 차감
        running_qty  -= t.quantity
return running_qty, running_cost   # 남은 수량·원가 → §4-2 평단 재계산에 그대로 사용
```

> **§4-2와 §4-3은 같은 replay를 공유한다.** `_recalc_item_from_transactions`(평단 재계산)가 `_recompute_realized_pnl`(실현손익 재박제)을 호출하고, 그 반환값(남은 수량/원가)으로 평단을 다시 잡는다. 거래 한 건 수정 → SELL 박제값 + 종목 평단/수량이 **한 번의 순회로 동시에** 바로잡힌다.

### 4-4. INVESTMENT 잔액 = 현금 + 보유 평가액 (03 §4-2 완결)

03에서 "투자 통장 잔액 공식은 portfolio 문서에서 완결"이라 미뤘던 부분. account 도메인이 portfolio repo를 불러 합산한다.

```python
# app/domain/account/service.py:312  _calc_investment_balance (03 §4-2 재인용)
cash = _cash_flow(start_balance, sums)          # (1) 입출금·이체 현금흐름
cash = cash - pt_sums["buy"] + pt_sums["sell"]  # (2) 매수 현금 -, 매도 현금 +
cost, valuation, pnl, rate = _summarize_holdings(items)  # (3) 보유종목 평가
balance = cash + valuation                       # ★ 총자산 = 남은 현금 + 보유 평가액
```

- **(2)의 `pt_sums`** = `PortfolioTransactionRepository.sum_for_accounts`(repository.py:291) — `GROUP BY account_id, pt_type`로 BUY/SELL 합을 **한 쿼리에** 가져옴(목록 N+1 차단).
- **(3)의 `items`** = `PortfolioItemRepository.find_active_by_account_ids`(repository.py:39) — 통장별 보유종목 배치 로드.

> 즉 통장 잔액 화면(03)이 보여주는 투자 통장 금액은, 이 도메인의 거래합·보유종목을 끌어다 만든다. **두 도메인의 접점**이 바로 이 공식.

### 4-5. 월별 평가액 박제 — `snapshot_service`

매달 종목별로 한 줄씩 박제해 추이 차트(§5 value-history)의 재료를 만든다.

```python
# app/domain/portfolio/snapshot_service.py  snapshot_household_portfolio(..., replace=False)
if replace:
    await repo.delete_for_household_month(household_id, snapshot_date)  # upsert: 기존 월 hard delete
for account in INVESTMENT_활성_통장:
    for item in 활성_종목:
        histories.append(PortfolioValueHistory(
            snapshot_date=snapshot_date,
            quantity=item.quantity, avg_price=item.avg_price,
            current_price=item.current_price,
            cost=item.quantity*item.avg_price,
            valuation=item.quantity*item.current_price,
        ))
await repo.save_all(histories)
```

- **멱등성** — `replace=True`면 그 달 박제를 **hard delete**(`delete_for_household_month`, repository.py:462) 후 재생성. soft delete가 아니라 진짜 삭제(중복 누적 방지).
- **호출처** — account_snapshot 도메인의 월간 박제 잡과 함께 돈다(스케줄러 5잡 중 월간 스냅샷, → **05 문서** §4-2). 이 문서는 "종목 평가액을 어떻게 박제하나"까지, 스케줄러 배선은 05가 정본.

### 4-6. 커서 무한 스크롤 + 기간 정규화 두 종류

**커서** — transaction 도메인과 동일 패턴(04 참조). 종목 거래 내역에 적용.
```python
# repository.py:394  _cursor_after — 커서 = "{tx_date}|{id}"
tx_date < cur_date  OR  (tx_date == cur_date AND id < cur_id)   # 복합 커서 tie-break
# repository.py: list_active_by_item_id_cursor — limit+1 조회 → has_next 판정
```

**기간 정규화 — 용도별로 둘** (헷갈리기 쉬운 지점)
| 함수 | 라인 | 정규화 | 쓰는 곳 |
|---|---|---|---|
| `_default_month_range` | service.py:774 | from/to를 **그달 1일**로 | 월별 평가액 추이(value-history) |
| `_default_day_range` | service.py:796 | **일 단위 그대로** | 매매손익(realized-pnl) |

> 둘 다 미지정 시 "최근 12개월". 하지만 추이 차트는 월 단위라 1일로 자르고, 매매손익은 "6/15~7/20" 같은 일 자유 필터라 안 자른다. 섞으면 안 돼서 함수를 분리했다.

---

## 5. 엔드포인트별 풀 트레이스 — `/portfolio` (17개, 6그룹)

전부 `CurrentHousehold`를 받는다(→ 02 §4): 로그인 + 그 가계부 멤버여야 진입. 실제 URL은 `root_path="/api"` + prefix → 예: `GET /api/portfolio/overview`. 거의 모든 핸들러가 `find_by_id` 후 **`item.household_id != household.id → NOT_FOUND`** 소유권 가드를 건다(남의 종목 ID 찍어도 안 보임).

### 그룹 A — 페이지 진입 (조회, 변경 없음)

**`GET /portfolio/overview`** — 포트폴리오 메인 (투자계좌 + 종목 + 요약)
```
요청  GET /api/portfolio/overview   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:41  household: CurrentHousehold
─[2] 서비스        service.py:545  get_portfolio_overview
      account_service.list_accounts → INVESTMENT 통장만 필터 (잔액공식 §4-4 적용됨)
      투자통장 없으면 _zero_summary 로 조기반환
      find_active_by_household_id (보유종목 전체) + _group_portfolios_by_account
      _summarize_investment_accounts → hero 합계(balance/cash/valuation/cost/profit/rate)
─[3] 응답 조립     service.py:569  PortfolioOverviewResponse(summary, investment_accounts[])
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(PortfolioOverviewResponse)
```

**`GET /portfolio/accounts/{account_id}/overview`** (router.py:51) — 계좌 상세 진입.
`account_service.get_account_detail` → INVESTMENT면 `find_active_by_account_id`로 보유종목 첨부, 아니면 `portfolios=[]`. household 필터 명시 재적용(service.py:598).

**`GET /portfolio/form-options`** (router.py:80) — 종목 등록 폼용. `list_accounts(account_type=INVESTMENT, is_archived=False)` 만 반환.

### 그룹 B — 종목 액션 (생성·매수·매도·수정·삭제) ★ 핵심

**`POST /portfolio/buy/{item_id}`** — 매수 (대표 풀 트레이스)
```
요청  POST /api/portfolio/buy/{id}  {quantity, price, txDate?, memo?}  + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:181  buy_portfolio
      PortfolioBuyRequest → model_validator(schema.py:78): quantity>0, price>0, 아니면 BAD_REQUEST
─[2] 서비스        service.py:126  buy
      find_by_id + household_id 가드 → NOT_FOUND
      (1) PortfolioTransaction(BUY) 이력 저장 (tx_date 미지정 시 today_kst)
      (2) 평단 가중평균 재계산 + quantity 누적                    → §4-2 ①
      db.flush (UPDATE 예약, commit은 아직)
─[3] 응답 조립     service.py:169  find_by_ids(통장) → _build_response (PNL 포함)  → §4-1
─[4] 트랜잭션 종료  get_db — commit (이력 INSERT + 종목 UPDATE 함께 확정)
응답  ApiResponse.ok(PortfolioResponse)
```

**`POST /portfolio/create`** (router.py:170 → service.py:98) — 종목 등록.
`_validate_investment_account`(service.py:703)로 "INVESTMENT 통장 + 같은 가계부" 검증 → `quantity=0, avg_price=0`으로 **메타만** 생성. 실제 보유는 buy로. `PortfolioCreateRequest`(schema.py:38): name 1~100, current_price>0, OTHER 아니면 code 1~50.

**`POST /portfolio/sell/{item_id}`** (router.py:205 → service.py:202) — 매도.
buy와 대칭이되 차이:
- `req.quantity > item.quantity`면 BAD_REQUEST (보유보다 많이 못 팖)
- 매도 시점 평단으로 **실현손익 박제**(`realized_pnl`/`realized_cost_basis`) → §4-3
- 평단 불변, 수량만 차감 → §4-2 ②
- **전량매도(remaining==0)면 종목 soft delete + 응답 `data=null`** (router 반환 타입이 `PortfolioResponse | None`)

**`PUT /portfolio/update/{item_id}`** (router.py:193 → service.py:173) — 평가액/메타 수정 (거래 무관).
`current_price`·name·code·market·is_archived 부분 수정. **보관(`is_archived=True`) 시 보유수량>0이면 `PORTFOLIO_HAS_HOLDINGS` 차단** — 전량 매도 후에만 보관 가능(service.py:192).

**`DELETE /portfolio/delete/{item_id}`** (router.py:240 → service.py:317) — 종목 soft delete.
**보유수량>0이면 `PORTFOLIO_HAS_HOLDINGS` 차단**(먼저 전량매도 필요). value_history 행은 **보존**(과거 추이 유지).

### 그룹 C — 거래 이력 수정/삭제/조회 ★ replay 트리거

**`PUT /portfolio/transactions/{tx_id}`** — 거래 수정 (replay 재계산)
```
요청  PUT /api/portfolio/transactions/{id}  {quantity?, price?, txDate?, memo?}  + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:217  PortfolioTxUpdateRequest(schema.py:125): qty/price 주면 >0. pt_type 변경 불가
─[2] 서비스        service.py:263  update_portfolio_transaction
      find_by_id + household 가드 → NOT_FOUND
      tx 필드 부분 수정 → db.flush
      portfolio_item_id 있으면 find_by_id_any_status(죽은 종목도) → _recalc_item_from_transactions
                                            ↑ 전체 거래 replay: 평단·실현손익·수량 동시 재계산  → §4-2③·§4-3
                                            ↑ 매도>매수면 BAD_REQUEST, qty 0→양수면 종목 부활
─[3] 응답 조립     service.py:292  _build_tx_response
─[4] 트랜잭션 종료  get_db — commit
응답  ApiResponse.ok(PortfolioTxResponse)
```

**`DELETE /portfolio/transactions/{tx_id}`** (router.py:229 → service.py:296) — 거래 soft delete.
`data_stat_cd=DELETED` → 동일하게 `_recalc_item_from_transactions` replay. "잘못 기록한 매수 1건 삭제" → 평단/수량이 그 거래 없던 것처럼 재계산됨.

**`GET /portfolio/items/{item_id}/transactions`** (router.py:106 → service.py:609) — 종목 거래 내역 무한 스크롤.
소유권 검증 → `list_active_by_item_id_cursor`(limit+1) → `next_cursor="{tx_date}|{id}"`, `has_next`. → §4-6. (`total_count=None` — 무한 스크롤은 카운트 안 씀)

### 그룹 D — 매매손익 (realized PnL 집계)

**`GET /portfolio/items/{item_id}/realized-pnl`** (router.py:121 → service.py:367) — 종목 매매손익.
`_default_day_range`(§4-6, 기본 12개월) → `find_sell_txs_by_item`로 기간 내 SELL만 조회 → 건별 `RealizedPnlRow`(손익·수익률) + 합계 `RealizedPnlSummary`. **구버전 NULL 실현손익은 0으로 간주**(service.py:393).

**`GET /portfolio/accounts/{account_id}/realized-pnl`** (router.py:62 → service.py:422) — 계좌 누적 매매손익.
종목 단위와 거의 같되 `find_sell_txs_by_account`로 계좌 전체 SELL 집계. **전량매도로 사라진 종목의 매도도 포함**(거래 이력은 남으니까 — 조회 사각지대 해소). row에 종목명(`name`) 채움(여러 종목 섞이므로).

### 그룹 E — 시세 조회/갱신 (외부 야후 연동)

**`GET /portfolio/lookup`** (router.py:141 → service.py:67) — 야후로 종목명+현재가 조회 (폼 자동채움, **저장 X**).
```
OTHER 시장 → STOCK_LOOKUP_FAILED (야후 미지원, 방어용 거부)
yahoo_lookup(market, code) → (name, price, symbol)
USD 시장(NASDAQ/NYSE)이면 → CurrencyRateRepository.find_by_pair(USD,KRW) 로 KRW 환산
                            환율 없으면 STOCK_LOOKUP_FAILED (평일 09:00 환율잡 선행 필요)
```
> DB의 `current_price`는 **항상 KRW**. USD 종목도 저장 전 환산한다. 환율/시세 인프라는 → **07 문서**(exchange_rate·market_price).

**`POST /portfolio/refresh-prices`** (router.py:154 → service.py:344) — 보유종목 현재가 즉시 갱신(수동 새로고침 버튼).
`market_price_service.refresh(_REFRESH_MARKETS, household_id=...)` 위임 — OTHER 제외 4시장. 반환: fetched/skipped/updated_rows. 시세 갱신 본체도 → **07 문서**.

### 그룹 F — 평가액 추이 차트 (value-history)

**`GET /portfolio/value-history`** (router.py:256 → service.py:475) — 통장 단위 종목별 월별 추이.
계좌 소유권 검증 → `_default_month_range`(§4-6) → `find_by_account_and_range` → **종목별 그루핑**. 삭제된 종목도 ticker 표시 위해 `find_by_ids_including_deleted`로 이름 채움(없으면 `"(삭제됨)"`).

**`GET /portfolio/items/{item_id}/value-history`** (router.py:269 → service.py:517) — 특정 종목 월별 추이.
`find_by_ids_including_deleted`로 삭제 종목도 조회 가능 → `find_by_item_and_range` → 단일 `PortfolioValueHistoryByItem`. 박제 데이터(§4-5)를 그대로 차트 포인트로.

---

## 6. 데이터 흐름 (도메인 큰 그림)

```
프론트 ──Bearer + X-Household-Id──▶ /portfolio/*
                                       │
                  CurrentHousehold ── 멤버십 + household_id 소유권 가드
                                       │
   ┌───────────────┬──────────────────┼───────────────┬─────────────────┐
 페이지진입       종목액션          거래수정/삭제      매매손익          시세/추이
 (overview)    (buy/sell/...)    (tx PUT/DELETE)  (realized-pnl)   (lookup/refresh/
   │               │                  │               │             value-history)
 잔액공식        평단 즉시계산      전체 replay      SELL 박제값       야후 환산 /
 §4-4 끌어옴      §4-2 ①②         §4-2③·§4-3       집계 §4-3        월별 박제 §4-5
   │               │                  │               │                 │
   │          이력 INSERT +      평단·실현손익                      current_price
   │          종목 UPDATE        동시 재계산                        UPDATE / 차트조회
   │               │                  │               │                 │
   └─────────────── get_db: 성공 commit / 예외 rollback ──────────────────┘
                                       │
              ┌────────────────────────┴───────────────────┐
        account 도메인 (03)                          07 문서
        투자통장 잔액 = 현금 + 평가액 (§4-4)          환율·시세 인프라 / 자산배분
```

거래 이력(PortfolioTransaction)이 **단일 진실의 원천** — 평단·수량·실현손익이 전부 여기서 파생/재계산된다. 종목 컬럼은 캐시일 뿐.

---

## 7. 이 문서에서 꼭 기억할 규칙

1. **3테이블 역할 분리** — `portfolio_items`(현재 상태·캐시) / `portfolio_transactions`(불변 이력·진실의 원천) / `portfolio_value_history`(월별 박제·추이).
2. **평단은 이동평균.** 매수=가중평균 즉시(§4-2①), 매도=평단 불변·수량만 차감(②), **거래 수정/삭제=전체 replay 재계산**(③). 진실은 항상 거래 이력.
3. **실현손익은 매도시점 평단으로 건별 박제**(§4-3). 거래 수정 시 같은 replay로 재박제 — 평단·실현손익이 한 순회로 동시 정정. 구버전 NULL은 0 간주.
4. **전량매도 = 종목 soft delete + 응답 null.** 보유수량>0이면 종목 삭제·보관 둘 다 차단(`PORTFOLIO_HAS_HOLDINGS`).
5. **INVESTMENT 잔액 = 현금 + 보유평가액**(§4-4) — 03에서 미뤘던 공식의 완결. account 도메인이 portfolio repo를 끌어다 배치 집계(N+1 차단).
6. **DB current_price는 항상 KRW.** USD 종목은 lookup/refresh 시 환율로 환산해 저장 — 시세/환율 인프라는 07.
7. **기간 정규화 둘** — 월 추이는 `_default_month_range`(1일로), 매매손익은 `_default_day_range`(일 그대로). 섞지 말 것.
8. 모든 API는 `CurrentHousehold` + `household_id` 소유권 가드 → 남의 투자 데이터 접근 불가.

---

## 다음 문서
➡ **`07-pricing-snapshot-wealth.md`** — 이 문서가 "환산은 07에서"로 넘긴 **환율(exchange_rate)·시세(market_price)** 의 내부 배치 메커니즘(라우터 미등록, 스케줄러 전용)과, 종목·수동자산·현금을 자산군(`AssetClass`)으로 묶어 배분 파이/추이를 만드는 **wealth** 를 본다.
