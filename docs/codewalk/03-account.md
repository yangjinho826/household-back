# 03. account — 통장, 그리고 "잔액은 저장하지 않는다"

> `X-Household-Id` 로 가계부에 들어오면, 그 안의 첫 하위 데이터가 **통장(account)** 이다. 모든 거래·매매·스냅샷은 결국 어느 통장에 매달린다. 이 문서의 백미는 두 가지 — ① **잔액(balance)을 컬럼에 저장하지 않고 매번 계산한다**, ② **`is_archived`(보관)** 와 **soft-delete(삭제)** 는 전혀 다른 개념이다.

> account는 household 다음으로 많이 참조되는 기반 도메인이다. 여기 잔액 공식을 잡아두면 04(거래)·05(스냅샷)·06(포트폴리오)가 전부 "이 공식에 뭘 더하고 빼는가" 로 읽힌다.

---

## 1. 이 도메인 한마디

가계부 안의 **통장 한 칸**. 생활비 통장, 적금, 투자 계좌, 심지어 부동산·연금 같은 "수동 자산"까지 전부 `Account` 한 테이블로 표현한다. 통장마다 **현재 잔액**을 보여주는 게 핵심이고, 그 잔액은 **거래 내역으로부터 계산**된다.

---

## 2. 들어가기 전 (개념 콕)

| 개념 | 한마디 |
|---|---|
| **파생값(derived) vs 저장값(stored)** | 잔액은 DB에 안 들고 있고(파생), `start_balance`(초기잔액)와 거래들로 **요청 때마다 계산**한다. |
| **`StrEnum`** | 값이 곧 문자열인 enum. `account_type` 을 DB엔 `"LIVING"` 문자열로 저장. |
| **소프트 삭제 vs 보관** | 삭제=`data_stat_cd="99"`(눈에서 사라짐). 보관=`is_archived=True`(살아있되 "안 씀" 표시). |
| **N+1 문제** | 통장 100개의 잔액을 각각 쿼리하면 100번. → 합계를 **한 번에** 가져와 막는다(섹션 4-4). |

---

## 3. 데이터 모델 — `accounts`

```python
# app/domain/account/model.py:10
class Account(BaseEntity):
    household_id:  Mapped[UUID]     # 소속 가계부 (논리 FK)
    name:          Mapped[str]      # String(100)
    account_type:  Mapped[str]      # String(20) — AccountType enum 값
    start_balance: Mapped[Decimal]  # Numeric(15,2) — 초기 잔액
    color:         Mapped[str|None] # "#RRGGBB"
    icon:          Mapped[str|None]
    sort_order:    Mapped[int]      # 화면 정렬 순서
    is_archived:   Mapped[bool]     # 보관 여부 (≠ 삭제)
```

`+ BaseEntity` (id·생성/수정일시·`data_stat_cd`).

> **잔액 컬럼이 없다.** 표에서 눈을 씻고 봐도 `balance` 가 없다. 의도된 설계 — 잔액은 `start_balance` + 거래합으로 **계산**한다(섹션 4-2). 저장하면 거래 추가/수정/삭제마다 동기화해야 하고 틀어질 위험이 있다. 계산식이 단일 진실(single source of truth).

### 통장 타입 8종 — `AccountType`

```python
# app/domain/account/enum.py:4
class AccountType(StrEnum):
    LIVING        = "LIVING"        # 생활
    SAVINGS       = "SAVINGS"       # 적립
    INVESTMENT    = "INVESTMENT"    # 투자 (주식 매매 — 잔액 공식 다름)
    REAL_ESTATE   = "REAL_ESTATE"   # 부동산  ┐
    PENSION       = "PENSION"       # 연금    │ 수동자산 (이체 전용)
    COMMODITY     = "COMMODITY"     # 금·원자재│
    SAVINGS_ASSET = "SAVINGS_ASSET" # 적금    ┘
    OTHER         = "OTHER"         # 기타
```

타입은 잔액 계산 방식 기준으로 **3그룹**으로 갈린다:

| 그룹 | 타입 | 거래 방식 | 잔액 공식 |
|---|---|---|---|
| **일반 현금** | LIVING·SAVINGS·OTHER | 수입/지출/이체 | `start_balance + 거래합` |
| **수동 자산** | REAL_ESTATE·PENSION·COMMODITY·SAVINGS_ASSET | 이체 + **평가조정** | `start_balance + 거래합(평가조정 포함)` |
| **투자** | INVESTMENT | 이체 + 주식매매 | `현금흐름 + 보유종목 평가액` |

```python
# app/domain/account/enum.py:19  — 수동자산 묶음 (프론트 분기·기본 메타에 사용)
MANUAL_ASSET_ACCOUNT_TYPES = (REAL_ESTATE, PENSION, COMMODITY, SAVINGS_ASSET)
```
수동자산은 생성 시 color/icon을 안 주면 타입별 기본값이 자동으로 붙는다(`MANUAL_ASSET_DEFAULT_META`).

### 다른 도메인에서의 참조 (account는 "소유 주체")
| 도메인 | 매다는 컬럼 | 관계 |
|---|---|---|
| transaction | `account_id`, `to_account_id`(이체) | 거래는 통장에 종속 |
| account_snapshot | `account_id` | 월말 잔액 박제 |
| portfolio (item·transaction·value_history) | `account_id` | 투자 통장에 종속 |

→ 통장 삭제 시 이들을 **cascade soft-delete** 한다(섹션 4-3).

---

## 4. 핵심 로직 코드리딩

### 4-1. is_archived vs soft-delete — 헷갈리기 쉬운 두 상태

| | `is_archived` (보관) | `data_stat_cd` (soft-delete) |
|---|---|---|
| 값 | `True` / `False` | `"50"` 활성 / `"99"` 삭제 |
| 의미 | "안 쓰지만 기록은 남김" | "없는 셈 친다" |
| 조회 | **여전히 조회됨** (필터로 구분) | NOT_FOUND (안 보임) |
| 자식 거래 | 그대로 유지 | cascade 삭제 |
| 트리거 | 사용자가 PUT으로 토글 | DELETE 엔드포인트 |

> 예: "작년에 해지한 적금" → 잔액 추이는 보고 싶으니 **보관(`is_archived=True`)**. "잘못 만든 통장" → **삭제(DELETE)**. `update_account`(service.py:158)에서 `is_archived` 를 켰다 껐다 한다.

### 4-2. 잔액 공식 — 이 문서의 핵심

진입점은 `_calc_balance` 하나, 타입 보고 전략을 고른다:

```python
# app/domain/account/service.py:271
async def _calc_balance(tx_repo, account, db) -> BalanceSummary:
    if account.account_type != AccountType.INVESTMENT:
        return await _calc_cash_balance(tx_repo, account)      # 일반·수동자산
    return await _calc_investment_balance(tx_repo, account, db)  # 투자만 별도
```

**① 일반/수동자산 — 현금흐름 공식**
```python
# app/domain/account/service.py:283
def _cash_flow(start_balance, sums) -> Decimal:
    return (
        start_balance
        + sums["income"]         # 수입        (+)
        - sums["expense"]        # 지출        (−)
        - sums["transfer_out"]   # 이체 출금    (−)
        + sums["transfer_in"]    # 이체 입금    (+)
        + sums["valuation_net"]  # 평가 조정    (방향대로, 수동자산용)
    )
```
> `sums` 는 **거래 테이블에서 통장별로 미리 합산해 온 값**(repository의 `sum_for_account`). 잔액 = 초기값에 수입 더하고 지출/출금 빼고 입금 더하고. 수동자산은 시세가 없으니 "평가조정"(직접 입력하는 가치 증감)을 더한다.

**② 투자(INVESTMENT) — 현금 + 보유종목 평가액**
```python
# app/domain/account/service.py:312
cash = _cash_flow(account.start_balance, sums)          # (1) 현금흐름 기본
cash = cash - pt_sums["buy"] + pt_sums["sell"]          # (2) 주식 매수 -, 매도 +
items = await PortfolioItemRepository(db).find_active_by_account_id(account.id)
cost, valuation, profit_loss, rate = _summarize_holdings(items)   # (3) 보유종목 평가
return BalanceSummary(
    balance = cash + valuation,    # ★ 총자산 = 남은 현금 + 보유종목 평가액
    cash = cash,
    portfolio_cost = cost, portfolio_valuation = valuation,
    portfolio_profit_loss = profit_loss, portfolio_profit_loss_rate = rate,
)
```
보유종목 평가는 순수 계산 함수 하나로:
```python
# app/domain/account/service.py:295  _summarize_holdings
cost      = Σ(수량 × 평단)         # 매입원가
valuation = Σ(수량 × 현재가)       # 평가액
profit_loss = valuation - cost     # 평가손익
rate = profit_loss / cost × 100    # 손익률 (cost>0 일 때만)
```

> ✅ 기억: **일반 통장 잔액 = `start_balance + 거래합`. 투자 통장 = `현금 + 보유종목 평가액`.** 어느 쪽도 DB에 저장된 값이 아니라 **요청 때 계산**된다.

### 4-3. 삭제 = cascade soft-delete (순서가 중요)

```python
# app/domain/account/service.py:187  delete_account
if await PortfolioItemRepository(db).count_active_by_account_id(account_id) > 0:
    raise CustomException(ErrorCode.ACCOUNT_HAS_DEPENDENTS)   # (1) 보유종목 있으면 삭제 차단

tx_repo = TransactionRepository(db)
await tx_repo.soft_delete_solo_by_account_id(account_id)               # (2) 이 통장만의 거래
await tx_repo.soft_delete_transfers_with_dead_counterparty(account_id) # (3) 양쪽 다 죽은 이체만
await PortfolioTransactionRepository(db).soft_delete_by_account_id(account_id)
await PortfolioValueHistoryRepository(db).soft_delete_by_account_id(account_id)
await AccountSnapshotRepository(db).soft_delete_by_account_id(account_id)
account.data_stat_cd = DataStatus.DELETED                              # (4) 본체도 삭제
```

세 가지 포인트:
- **(1) 보유종목이 있으면 막는다** — 투자 데이터를 통장 삭제로 날리지 않게.
- **(3) 이체는 특별 취급** — A→B 이체에서 A만 지우면, **B 입장의 입금 기록은 살려둬야** B 잔액이 안 망가진다. 그래서 "상대 통장도 죽은 이체"만 지운다.
- **(2)(3) 본체보다 자식 이체를 먼저** 처리 — 본체가 먼저 죽으면 "상대가 살았는지" 판정이 꼬인다.

### 4-4. 목록 잔액 — N+1 방지 배치 로드

목록 화면은 통장이 여러 개다. 각각 `_calc_balance` 를 돌리면 통장 수만큼 쿼리가 터진다. 그래서 합계를 **한 번에** 긁어온다:

```python
# app/domain/account/service.py:335  _load_balance_sources
ids     = [a.id for a in accounts]
inv_ids = [a.id for a in accounts if a.account_type == INVESTMENT]
tx_sums   = await TransactionRepository(db).sum_for_accounts(ids)            # 1쿼리
pt_sums   = await PortfolioTransactionRepository(db).sum_for_accounts(inv_ids)  # 1쿼리
items_map = await PortfolioItemRepository(db).find_active_by_account_ids(inv_ids)  # 1쿼리
```

| | 나이브 | 배치 |
|---|---|---|
| 통장 100개 | 1 + 100 + 100 = **201쿼리** | 1 + 3 = **4쿼리** |

> 01에서 본 N+1 회피 원칙의 실제 적용. 단건 조회(`get_account_detail`)는 `_calc_balance`, 목록은 `_load_balance_sources` + `_build_balance` 로 갈라진다.

---

## 5. API 엔드포인트 — `/account` (전부 `CurrentHousehold`)

| Method | Path | 설명 |
|---|---|---|
| GET | `/account/list` | 목록 (커서 무한스크롤, 타입·보관·검색어 필터) |
| POST | `/account/create` | 생성 (수동자산은 color/icon 자동) |
| GET | `/account/detail/{id}` | 단건 (잔액 + 투자면 PNL) |
| GET | `/account/report/{id}` | 월별 수입/지출 추이 (최근 12개월 + 이번달) |
| PUT | `/account/update/{id}` | 수정 (`is_archived` 토글 포함) |
| DELETE | `/account/delete/{id}` | cascade soft-delete |

> 모든 엔드포인트가 `CurrentHousehold` 를 받는다 = **로그인 + 그 가계부 멤버**여야 통장에 접근(→ 02 문서). 그리고 서비스마다 `account.household_id != household.id` 면 `NOT_FOUND` — 남의 가계부 통장 ID를 찍어도 안 보인다.

`/account/report` 의 월별 추이는 **박제 + 실시간 혼합**이다: 지난 달은 `AccountSnapshot`(스케줄러가 박제, →05 문서)에서 읽고, **이번 달은 거래에서 실시간 집계**해 합친다.

---

## 6. 데이터 흐름

```
GET /api/account/list   Bearer <access>  +  X-Household-Id: <id>
   │
   ├ CurrentHousehold ── 멤버십 검증 (아니면 HH001)
   ├ repo.list_by_cursor ── 통장 N개 (frst_reg_dt DESC, 커서)
   ├ _load_balance_sources ── 거래합·매매합·보유종목 3쿼리 (N+1 차단)
   └ 각 통장마다 _build_balance ── start_balance + 거래합 (+투자면 평가액)
   ← CursorPage[AccountResponse]  (balance·is_archived·투자면 PNL 포함)

POST /api/account/create  {name, accountType, startBalance}
   ├ sort_order = max+1,  수동자산이면 color/icon 자동
   └ INSERT (is_archived=False, data_stat_cd=ACTIVE)
   ← AccountResponse  (갓 만든 통장: balance == startBalance)

DELETE /api/account/delete/{id}
   ├ 보유종목 있으면 → ACCOUNT_HAS_DEPENDENTS (차단)
   └ 자식(거래·이체·포트폴리오·스냅샷) cascade soft-delete → 본체 DELETED
```

---

## 7. 이 문서에서 꼭 기억할 규칙

1. **잔액은 저장 안 한다.** `balance` 컬럼 없음 — `start_balance + 거래합`(투자는 `현금 + 평가액`)으로 **요청 때 계산**. 계산식이 단일 진실.
2. **타입 8종 = 잔액 공식 3그룹.** 일반현금 / 수동자산(이체+평가조정) / 투자(매매+평가액). 분기는 `_calc_balance`.
3. **`is_archived`(보관) ≠ soft-delete(삭제).** 보관은 살아서 조회됨, 삭제는 cascade로 자식까지 사라짐.
4. **삭제는 순서가 핵심**: 보유종목 있으면 차단 → 이체는 상대 살아있으면 보존 → 본체 마지막.
5. **목록은 배치 로드로 N+1 차단** (통장 수 무관 +3쿼리). 단건은 `_calc_balance`.
6. 모든 통장 API는 `CurrentHousehold` + `household_id` 일치 검사 → 남의 가계부 통장 접근 불가.

---

## 다음 문서
➡ **`04-category-transaction.md`** — 통장 잔액을 움직이는 주체, **거래(transaction)**. 여기서 본 `income/expense/transfer_in/transfer_out/valuation_net` 합계가 실제로 어떻게 쌓이는지, 카테고리 분류와 이체의 양방향 처리를 본다.
