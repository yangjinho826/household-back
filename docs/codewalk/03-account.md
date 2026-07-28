# 03. account — 통장, 그리고 "잔액은 저장하지 않는다"

> `X-Household-Id` 로 가계부에 들어오면, 그 안의 첫 하위 데이터가 **통장(account)** 이다. 모든 거래·매매·스냅샷은 결국 어느 통장에 매달린다. 이 문서의 백미 둘 — ① **잔액(balance)을 컬럼에 저장하지 않고 매번 계산한다**, ② **`is_archived`(보관)** 와 **soft-delete(삭제)** 는 전혀 다른 개념이다.

> **이 문서 읽는 법:** §4(공통 메커니즘)에 잔액 공식·커서·삭제 같은 "여러 API가 공유하는 로직"을 한 번 깊게 정리했다. §5(엔드포인트별 트레이스)는 통장 API 6개를 **요청부터 응답까지** 한 줄기로 따라가며, 공통 로직은 `→ §4-x` 로 참조한다. 특정 API만 궁금하면 §5에서 그 API 블록만 봐도 된다.

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
| **N+1 문제** | 통장 100개의 잔액을 각각 쿼리하면 100번. → 합계를 **한 번에** 가져와 막는다(§4-2). |
| **커서 페이징** | 페이지 번호 대신 "마지막 본 지점(커서)" 으로 다음 묶음을 가져오는 무한 스크롤(§4-3). |

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

> **잔액 컬럼이 없다.** 표를 눈 씻고 봐도 `balance` 가 없다. 의도된 설계 — 잔액은 `start_balance` + 거래합으로 **계산**한다(§4-2). 저장하면 거래 추가/수정/삭제마다 동기화해야 하고 틀어질 위험이 있다. 계산식이 단일 진실(single source of truth).

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

> 응답(`AccountResponse`)엔 `is_manual_asset`(수동자산 4종이면 `True`)이 **계산돼 실린다** — DB 컬럼이 아니라 `_build_response`(service.py:384)가 `account_type in MANUAL_ASSET_ACCOUNT_TYPES` 로 매번 판정. 프론트는 이 값으로 거래폼에서 "이체만" 노출할지 분기한다.

### 다른 도메인에서의 참조 (account는 "소유 주체")
| 도메인 | 매다는 컬럼 | 관계 |
|---|---|---|
| transaction | `account_id`, `to_account_id`(이체) | 거래는 통장에 종속 |
| account_snapshot | `account_id` | 월말 잔액 박제 |
| portfolio (item·transaction·value_history) | `account_id` | 투자 통장에 종속 |

→ 통장 삭제 시 이들을 **cascade soft-delete** 한다(§4-4).

---

## 4. 공통 메커니즘

통장 API들이 공유하는 로직을 여기 모았다. §5 트레이스가 이 절들을 참조한다.

### 4-1. is_archived(보관) vs soft-delete(삭제)

| | `is_archived` (보관) | `data_stat_cd` (soft-delete) |
|---|---|---|
| 값 | `True` / `False` | `"50"` 활성 / `"99"` 삭제 |
| 의미 | "안 쓰지만 기록은 남김" | "없는 셈 친다" |
| 조회 | **여전히 조회됨** (필터로 구분) | NOT_FOUND (안 보임) |
| 자식 거래 | 그대로 유지 | cascade 삭제 |
| 트리거 | 사용자가 PUT으로 토글 | DELETE 엔드포인트 |

> 예: "작년에 해지한 적금" → 잔액 추이는 보고 싶으니 **보관(`is_archived=True`)**. "잘못 만든 통장" → **삭제(DELETE)**. `update_account`(service.py:178)에서 `is_archived` 를 켰다 껐다 한다.

### 4-2. 잔액 공식 — 이 도메인의 심장

진입점 `_calc_balance` 가 타입 보고 전략을 고른다:

```python
# app/domain/account/service.py:271
async def _calc_balance(tx_repo, account, db) -> BalanceSummary:
    if account.account_type != AccountType.INVESTMENT:
        return await _calc_cash_balance(tx_repo, account)        # 일반·수동자산
    return await _calc_investment_balance(tx_repo, account, db)  # 투자만 별도
```

**① 일반/수동자산 — 현금흐름 공식**
```python
# app/domain/account/service.py:283  _cash_flow
return (
    start_balance
    + sums["income"]         # 수입        (+)
    - sums["expense"]        # 지출        (−)
    - sums["transfer_out"]   # 이체 출금    (−)
    + sums["transfer_in"]    # 이체 입금    (+)
    + sums["valuation_net"]  # 평가 조정    (방향대로, 수동자산용)
)
```
> `sums` 는 **거래 테이블에서 통장별로 미리 합산해 온 값**(repository의 `sum_for_account`). 수동자산은 시세가 없으니 "평가조정"(직접 입력하는 가치 증감)을 더한다.

**② 투자(INVESTMENT) — 현금 + 보유종목 평가액**
```python
# app/domain/account/service.py:312  _calc_investment_balance
cash = _cash_flow(account.start_balance, sums)          # (1) 현금흐름 기본
cash = cash - pt_sums["buy"] + pt_sums["sell"]          # (2) 주식 매수 -, 매도 +
cost, valuation, profit_loss, rate = _summarize_holdings(items)   # (3) 보유종목 평가
balance = cash + valuation        # ★ 총자산 = 남은 현금 + 보유종목 평가액
```
보유종목 평가(`_summarize_holdings`, service.py:295): `cost=Σ(수량×평단)`, `valuation=Σ(수량×현재가)`, `profit_loss=valuation−cost`, `rate=profit_loss/cost×100`(cost>0).

**같은 공식, 두 구현 — `_calc_balance` ↔ `_build_balance`**

| 함수 | 쓰는 곳 | 데이터 출처 | 쿼리 수 |
|---|---|---|---|
| `_calc_balance`(:271) | 단건 (detail·update·report) | 그 통장 합계를 **즉석 쿼리** | 통장당 2~3 |
| `_build_balance`(:347) | 목록 (list) | `_load_balance_sources` 가 미리 받은 **배치 dict** | 통장 수 무관 |

```python
# 단건: service.py:308  — 그 통장 합계를 즉석 쿼리
sums = await tx_repo.sum_for_account(account.id)
# 목록: service.py:354  — 이미 배치로 받아둔 dict에서 꺼내기만 (쿼리 X)
s = tx_sums[account.id]
```
배치 로드(N+1 차단)는 통장 수와 무관하게 **3쿼리**:
```python
# app/domain/account/service.py:335  _load_balance_sources
tx_sums   = await TransactionRepository(db).sum_for_accounts(ids)             # 1쿼리: 거래합
pt_sums   = await PortfolioTransactionRepository(db).sum_for_accounts(inv_ids)  # 1쿼리: 매매합
items_map = await PortfolioItemRepository(db).find_active_by_account_ids(inv_ids)  # 1쿼리: 보유종목
```

> ✅ 기억: 잔액은 **저장이 아니라 계산**. 공식은 하나(`_cash_flow`)지만 구현이 둘 — 단건은 즉석 쿼리, 목록은 배치 dict로 N+1 차단. 공식 바뀌면 **둘 다** 손봐야 한다.

### 4-3. 커서 무한 스크롤

목록(`GET /account/list`)은 페이지 번호가 아니라 커서로 다음 묶음을 가져온다.

```python
# app/domain/account/repository.py:82  _cursor_after — 커서 = "{frst_reg_dt}|{id}" 복합값
return or_(
    Account.frst_reg_dt < cur_dt,                              # 더 과거 행
    and_(Account.frst_reg_dt == cur_dt, Account.id < cur_id),  # ① 같은 시각이면 id로 tie-break
)
# repository.py:122
.limit(limit + 1)            # ② limit보다 1개 더 요청
# service.py:91
has_next = len(rows) > limit # 31개 왔으면 "다음 있음", 30개로 잘라 응답
```
> ① **복합 커서** — `frst_reg_dt` 만으로 자르면 같은 시각 행에서 중복·누락이 난다. `id` 를 2차 키로 묶어 막는다. ② **`limit+1` 트릭** — 한 개 더 가져와 그 존재로 `has_next` 판정 → 다음 페이지 유무 알려고 별도 count 쿼리 안 침.

> **정렬이 두 가지다.** 내부용 `list_accounts`(:51)는 `sort_order`(사용자가 정한 통장 순서), 외부 API용 `list_accounts_cursor`(:71)는 `frst_reg_dt DESC`(최신순). 화면 줄세우기엔 사용자 순서가, 무한 스크롤엔 "만든 순"이 안정적이라서다.

### 4-4. cascade 삭제 — 순서가 중요

```python
# app/domain/account/service.py:187  delete_account
if await PortfolioItemRepository(db).count_active_by_account_id(account_id) > 0:
    raise CustomException(ErrorCode.ACCOUNT_HAS_DEPENDENTS)   # (1) 보유종목 있으면 삭제 차단
await tx_repo.soft_delete_solo_by_account_id(account_id)               # (2) 이 통장만의 거래
await tx_repo.soft_delete_transfers_with_dead_counterparty(account_id) # (3) 양쪽 다 죽은 이체만
await PortfolioTransactionRepository(db).soft_delete_by_account_id(account_id)
await PortfolioValueHistoryRepository(db).soft_delete_by_account_id(account_id)
await AccountSnapshotRepository(db).soft_delete_by_account_id(account_id)
account.data_stat_cd = DataStatus.DELETED                              # (4) 본체도 삭제
```
- **(1) 보유종목 있으면 막는다** — 투자 데이터를 통장 삭제로 날리지 않게.
- **(3) 이체 특별 취급** — A→B 이체에서 A만 지우면 **B 입장의 입금 기록은 살려둬야** B 잔액이 안 망가진다. 그래서 "상대도 죽은 이체"만 지운다.
- **(2)(3) 본체보다 자식 이체를 먼저** — 본체가 먼저 죽으면 "상대가 살았는지" 판정이 꼬인다.

> 02의 **가계부** 삭제는 통째로 사라지므로 "순서 무관"이었다. 여기 **통장** 삭제는 이체 때문에 "순서 중요" — 대비해서 기억.

### 4-5. 리포트 — 박제된 과거 + 실시간 이번달

```python
# app/domain/account/service.py:247  get_account_report
snaps = await AccountSnapshotRepository(db).find_by_account_and_range(account_id, from_date, to_date)
flows = [_snapshot_to_flow(s) for s in snaps]          # (1) 지난 달들: 박제 스냅샷 (고정값)
summary = await _calc_balance(tx_repo, account, db)    # (2) 현재 잔액
if to_date >= this_month_first and (이번달 스냅샷 없으면):
    flows.append(await _current_month_flow(...))       # (3) 이번달: 거래 실시간 집계
```
- **(1) 지난 달** = `AccountSnapshot`(스케줄러가 매월 1일 박제, →05 문서)에서 읽은 **고정값**.
- **(3) 이번 달** = 아직 박제 전이라 거래에서 **실시간 집계**(`_current_month_flow`).
- 기본 기간 = **최근 12개월**: `_report_range`(:404)가 to 미지정 시 이번달, from 미지정 시 to−11개월.

> "과거는 박제, 현재는 계산"은 이 앱의 반복 패턴 — 통장 잔액(§4-2)과 같은 철학.

---

## 5. 엔드포인트별 풀 트레이스 — `/account`

전부 `CurrentHousehold` 를 받는다(→ 02 §4). 즉 **로그인 + 그 가계부 멤버**여야 진입. 실제 URL은 `root_path="/api"` + prefix → 예: `GET /api/account/list`.

### GET /account/list — 통장 목록 (무한 스크롤)
```
요청  GET /api/account/list?limit=30&accountType=&isArchived=   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:23  list_accounts
      household: CurrentHousehold → 토큰 디코드 → 멤버십 조회, 아니면 HH001 (요청 거부)
      q: AccountListQuery(Query) → limit 1~200 검증(schema.py:21), accountType enum 파싱
─[2] 서비스        service.py:71  list_accounts_cursor
      repo.list_by_cursor (repository.py:98) → frst_reg_dt DESC, limit+1 조회   → §4-3
      _load_balance_sources (service.py:335) → 거래합·매매합·보유종목 3쿼리        → §4-2 (N+1 차단)
      각 통장 _build_balance → _cash_flow 공식                                  → §4-2
      next_cursor = "{마지막행.frst_reg_dt}|{id}",  has_next = len>limit
      count_search (repository.py:126) → total_count (관리 페이지 'N개' 표시용)
─[3] 응답 조립     service.py:95  _build_response × N → AccountResponse(balance·is_manual_asset·투자면 PNL)
─[4] 트랜잭션 종료  get_db — 조회뿐이라 변경 없음, 정상 종료
응답  ApiResponse.ok(CursorPage[AccountResponse])
```

### POST /account/create — 통장 생성
```
요청  POST /api/account/create  {name, accountType, startBalance, color?, icon?}  + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:41  create_account
      household: CurrentHousehold (멤버십)
      AccountCreateRequest → model_validator(schema.py:35): name 1~100자, color ≤7자, 아니면 BAD_REQUEST
─[2] 서비스        service.py:117  create_account
      sort_order = req.sort_order ?? (repo.max_sort_order(household.id)+1)  ← SELECT MAX(sort_order) (repository.py:154)
      수동자산 타입이면 color/icon 미지정 시 MANUAL_ASSET_DEFAULT_META 자동 부여
      Account(... is_archived=False, data_stat_cd=ACTIVE) → repo.save → session.add + flush (id 채워짐, commit은 아직)
─[3] 응답 조립     service.py:144
      갓 생성 = 거래 0건 → balance == start_balance,  INVESTMENT면 PNL 0으로 채움
      _build_response → AccountResponse
─[4] 트랜잭션 종료  get_db — 예외 없으면 commit (여기서 실제 INSERT 확정)
응답  ApiResponse.ok(AccountResponse)
```

### GET /account/detail/{account_id} — 단건 (잔액 + PNL)
```
요청  GET /api/account/detail/{id}   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:52  household: CurrentHousehold
─[2] 서비스        service.py:214  get_account_detail
      repo.find_by_id (repository.py:15) → SELECT … WHERE id=? AND data_stat_cd=ACTIVE
      가드: 없거나 / household_id 불일치 / 비활성 → NOT_FOUND   ← 남의 가계부 통장 ID 찍어도 안 보임
      _calc_balance (즉석 쿼리)                                → §4-2
─[3] 응답 조립     service.py:224  _build_response → AccountResponse
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(AccountResponse)
```

### GET /account/report/{account_id} — 월별 수입/지출 추이
```
요청  GET /api/account/report/{id}   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:63  household: CurrentHousehold
─[2] 서비스        service.py:227  get_account_report
      find_by_id + 소유·활성 가드 → NOT_FOUND
      기간 정규화 _report_range → 기본 최근 12개월(이번달 포함)        → §4-5
      박제 스냅샷 조회 + 현재 잔액 _calc_balance + 이번달 실시간 집계   → §4-5
─[3] 응답 조립     service.py:262  AccountReportResponse(balance + monthly_flows[])
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(AccountReportResponse)
```

### PUT /account/update/{account_id} — 수정 (보관 토글 포함)
```
요청  PUT /api/account/update/{id}  {name?, accountType?, isArchived?, …}  + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:74  household: CurrentHousehold
      AccountUpdateRequest → model_validator(schema.py:53): name 주면 1~100, color 주면 ≤7
─[2] 서비스        service.py:158  update_account
      find_by_id + household_id 일치 가드 → NOT_FOUND
      None 아닌 필드만 부분 수정 (is_archived 포함 → 보관/해제 토글)   → §4-1
      db.flush → 변경 반영 (commit은 요청 끝)
─[3] 응답 조립     service.py:183  _calc_balance 재계산 → _build_response (수정 후 최신 잔액)
─[4] 트랜잭션 종료  get_db — commit (UPDATE 확정)
응답  ApiResponse.ok(AccountResponse)
```

### DELETE /account/delete/{account_id} — cascade soft-delete
```
요청  DELETE /api/account/delete/{id}   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:86  household: CurrentHousehold
─[2] 서비스        service.py:187  delete_account
      find_by_id + household_id 일치 가드 → NOT_FOUND
      보유종목 있으면 → ACCOUNT_HAS_DEPENDENTS (차단)                 → §4-4
      자식(거래·이체·포트폴리오·스냅샷) cascade soft-delete → 본체 DELETED  → §4-4 (순서 중요)
─[3] 응답 조립     반환값 없음 (None)
─[4] 트랜잭션 종료  get_db — commit (모든 soft-delete UPDATE를 한 트랜잭션으로 확정)
응답  ApiResponse.ok()   (data 없음)
```

---

## 6. 데이터 흐름 (도메인 큰 그림)

```
프론트 ──Bearer + X-Household-Id──▶ /account/*
                                       │
                  CurrentHousehold ── 멤버십 검증 (아니면 HH001)
                                       │
        ┌──────────────────────────────┼───────────────────────────────┐
   조회(list/detail/report)        변경(create/update)            삭제(delete)
        │                              │                               │
   잔액 계산(§4-2)                 INSERT/UPDATE + flush           cascade soft-delete(§4-4)
   (목록은 배치 N+1차단)            잔액 재계산                      보유종목 있으면 차단
        │                              │                               │
        └──────────── get_db: 성공 commit / 예외 rollback ─────────────┘
                                       │
                            ApiResponse 봉투로 응답
```

거래합(`income/expense/transfer/valuation_net`)이 **어떻게 쌓이는지**는 다음 문서(transaction)에서. 여기선 "이미 합산된 값을 받아 잔액을 만든다"까지.

---

## 7. 이 문서에서 꼭 기억할 규칙

1. **잔액은 저장 안 한다.** `balance` 컬럼 없음 — `start_balance + 거래합`(투자는 `현금 + 평가액`)으로 **요청 때 계산**(§4-2). 계산식이 단일 진실.
2. **타입 8종 = 잔액 공식 3그룹.** 일반현금 / 수동자산(이체+평가조정) / 투자(매매+평가액). 분기는 `_calc_balance`.
3. **공식 하나, 구현 둘.** 단건은 `_calc_balance`(즉석 쿼리), 목록은 `_build_balance`(배치 dict, N+1 차단).
4. **`is_archived`(보관) ≠ soft-delete(삭제)**(§4-1). 보관은 조회됨, 삭제는 cascade로 자식까지 사라짐.
5. **삭제는 순서가 핵심**(§4-4): 보유종목 있으면 차단 → 이체는 상대 살아있으면 보존 → 본체 마지막.
6. 모든 통장 API는 `CurrentHousehold` + `household_id` 일치 검사 → 남의 가계부 통장 접근 불가.

---

## 다음 문서
➡ **`04-category-transaction.md`** — 통장 잔액을 움직이는 주체, **거래(transaction)**. §4-2에서 "이미 합산됐다"고 넘긴 `income/expense/transfer_in/transfer_out/valuation_net` 이 실제로 어떻게 쌓이는지, 카테고리 분류와 이체의 양방향 처리를 본다.
