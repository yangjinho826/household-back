# 04. category·transaction — 통장을 움직이는 "거래", 그리고 그걸 분류하는 "카테고리"

> 03에서 통장 잔액을 `start_balance + 거래합` 으로 **계산**한다고 했고, 그 "거래합"(`income / expense / transfer_in / transfer_out / valuation_net`)은 "이미 합산됐다"며 넘겼다. 이 문서가 그 빈칸을 채운다 — **거래(transaction)** 가 어떻게 쌓여 통장 잔액을 움직이는지. 백미 셋: ① **이체는 한 줄(row)** 로 저장하고 부호는 조회할 때 계산한다, ② **거래 종류(tx_type) 5종**이 잔액·통계에 제각각 다르게 반영된다, ③ **카테고리 삭제는 거래를 건드리지 않는다**(orphan 허용).

> **이 문서 읽는 법:** §4(공통 메커니즘)에 거래 5종·부호·거래합·이체·러닝밸런스 같은 "여러 API가 공유하는 로직"을 한 번 깊게 정리했다. §5(엔드포인트별 트레이스)는 카테고리 5개 + 거래 8개 API를 **요청부터 응답까지** 한 줄기로 따라가며 공통 로직은 `→ §4-x` 로 참조한다. 특정 API만 궁금하면 §5에서 그 블록만 봐도 된다.

---

## 1. 이 도메인 한마디

**거래(transaction)** 는 통장에 일어나는 모든 돈의 움직임 — 수입·지출·이체·고정지출·평가조정. 통장 잔액(03)은 결국 이 거래들의 합이다. **카테고리(category)** 는 그 거래에 "식비·급여" 같은 꼬리표를 붙여 통계·차트를 가능하게 하는 분류표다. 거래가 주연, 카테고리는 조연.

---

## 2. 들어가기 전 (개념 콕)

| 개념 | 한마디 |
|---|---|
| **거래 5종(`TxType`)** | EXPENSE(지출)·INCOME(수입)·TRANSFER(이체)·FIXED_EXPENSE(고정지출)·VALUATION(평가조정). 종류마다 잔액·통계 반영 규칙이 다르다(§4-1). |
| **이체는 한 줄** | A→B 이체를 출금/입금 두 줄로 나누지 않는다. `account_id`(A)·`to_account_id`(B) 를 가진 **한 row**. 부호는 조회 때 계산(§4-3). |
| **부호 금액(signed_amount)** | DB의 `amount` 는 항상 양수. "이 통장 관점에서 +인지 −인지"는 조회 시 `_signed_amount` 가 판정(§4-3). |
| **거래합(sums dict)** | `sum_for_account` 가 통장별로 종류별 합계를 미리 내준 dict. 03의 잔액 공식이 받던 바로 그 값(§4-2). |
| **러닝 밸런스** | 거래 원장(ledger)에서 각 줄에 "그 거래 직후 잔액"을 붙여 보여주는 것. 역산으로 만든다(§4-5). |
| **평가조정(VALUATION)** | 부동산·연금 같은 수동자산의 "현금 없는 가치 증감"(시세·이자). 잔액엔 반영, **모든 통계에선 제외**(§4-1). |
| **orphan(고아) 허용** | 카테고리를 지워도 그 카테고리를 쓰던 거래는 그대로 둔다 — `category_id` 가 죽은 카테고리를 가리켜도 OK(§4-6). |

---

## 3. 데이터 모델

### 3-1. `categories` — 분류표 (단순)

```python
# app/domain/category/model.py:9
class Category(BaseEntity):
    household_id: Mapped[UUID]      # 소속 가계부 (논리 FK)
    kind:         Mapped[str]       # String(10) — "EXPENSE" / "INCOME" (CheckConstraint)
    name:         Mapped[str]       # String(100)
    color:        Mapped[str|None]  # "#RRGGBB"
    icon:         Mapped[str|None]
    sort_order:   Mapped[int]       # 화면 정렬 순서
    is_archived:  Mapped[bool]      # 보관 여부 (03의 통장과 같은 개념)
```

```python
# app/domain/category/model.py:13  — 테이블 제약
CheckConstraint("kind IN ('EXPENSE', 'INCOME')", name="ck_categories_kind")   # DB가 kind 값 강제
Index("idx_categories_household", "household_id", "kind")                       # 가계부+종류 조회 가속
```

> **계층 없음.** 부모-자식 카테고리(대분류/소분류) 구조가 **없다**. 평탄한 목록 하나. **기본 카테고리 자동 생성도 없다** — 가계부를 새로 만들어도(02) 카테고리는 0개에서 시작, 사용자가 직접 추가한다.

### 3-2. `transactions` — 거래 (이 문서의 주역)

```python
# app/domain/transaction/model.py:11
class Transaction(BaseEntity):
    household_id:        Mapped[UUID]      # 소속 가계부 (논리 FK)
    tx_type:             Mapped[str]       # String(20) — TxType 5종
    amount:              Mapped[Decimal]   # Numeric(15,2) — 항상 양수
    tx_date:             Mapped[date]      # 거래일
    account_id:          Mapped[UUID]      # 출금/수입/평가 대상 통장 (논리 FK)
    to_account_id:       Mapped[UUID|None] # 이체 도착 통장 (TRANSFER만, 논리 FK)
    category_id:         Mapped[UUID|None] # 분류 (논리 FK, 이체는 없음)
    paid_by_user_id:     Mapped[UUID|None] # 결제한 멤버 (가계부 공동사용용)
    fixed_expense_id:    Mapped[UUID|None] # ForeignKey("fixed_expenses.id", ondelete="SET NULL") ★유일한 실제 FK
    memo:                Mapped[str|None]  # Text
    valuation_direction: Mapped[str|None]  # String(20) — VALUATION만 INCREASE/DECREASE
```

```python
# app/domain/transaction/model.py:15  — 인덱스 5종 (조회 패턴별)
Index("idx_tx_household_date", "household_id", text("tx_date DESC"))  # 가계부 최신순 목록
Index("idx_tx_account", "account_id")          # 통장 원장
Index("idx_tx_to_account", "to_account_id")    # 이체 입금 쪽 조회
Index("idx_tx_category", "category_id")         # 카테고리별 통계
Index("idx_tx_date", text("tx_date DESC"))
```

> **실제 ForeignKey 제약은 `fixed_expense_id` 단 하나다**(model.py:32, `ondelete="SET NULL"`). `account_id`·`to_account_id`·`category_id`·`household_id` 는 전부 **논리 FK** — DB 제약 없이 컬럼만 두고 소속 검증은 서비스 코드가 한다(§4-4). 근거: `ddl/init.sql` 의 transactions 정의(전부 `-- logical FK` 주석) + alembic `b5375d2ae3a6`(is_fixed 컬럼을 fixed_expense_id 로 교체하며 `fk_transactions_fixed_expense_id` FK 추가). 이 프로젝트 전체가 "논리 FK + 서비스 검증" 기조인데(01·03 참조) transaction 만 예외적으로 진짜 FK 하나를 가진 셈 — 고정지출 삭제 시 거래의 매핑을 자동 NULL 처리하려고.

### 3-3. 거래 종류 `TxType` 5종 — 이 문서의 뼈대

```python
# app/domain/transaction/enum.py:4
class TxType(StrEnum):
    EXPENSE       = "EXPENSE"        # 지출
    INCOME        = "INCOME"         # 수입
    TRANSFER      = "TRANSFER"       # 이체 (통장→통장)
    FIXED_EXPENSE = "FIXED_EXPENSE"  # 고정지출 — fixed_expense_id 필수, 통계는 지출로 집계
    VALUATION     = "VALUATION"      # 평가조정 — 수동자산 가치 증감, 통계 제외

# app/domain/transaction/enum.py:17
class ValuationDirection(StrEnum):
    INCREASE = "INCREASE"   # 가치 상승 (+)
    DECREASE = "DECREASE"   # 가치 하락 (−)
```

종류별 "필수 동반 필드"와 "반영 방식"이 다르다 — 이게 검증(§4-4)·부호(§4-3)·통계의 분기 기준 전부다:

| 종류 | 필수 필드 | 금지 필드 | 통장 잔액 반영 | 통계 집계 | 카테고리 |
|---|---|---|---|---|---|
| **EXPENSE** | — | to_account_id | `− amount` | 지출 | EXPENSE 종류 |
| **INCOME** | — | to_account_id | `+ amount` | 수입 | INCOME 종류 |
| **TRANSFER** | to_account_id | category_id·fixed_expense_id | 출금통장 `−`, 입금통장 `+` | 이체 | 없음 |
| **FIXED_EXPENSE** | fixed_expense_id | to_account_id | `− amount` | **지출**(EXPENSE와 합산) | EXPENSE 종류 |
| **VALUATION** | valuation_direction | to_account_id·category_id | 방향대로 `±amount` | **제외** | 없음 |

> **두 가지가 입문자를 헷갈리게 한다.** ① FIXED_EXPENSE 는 EXPENSE 와 잔액·통계에서 **똑같이 지출**로 취급된다(차이는 "어떤 고정지출 항목에 매달렸나"뿐, →05). ② VALUATION 은 잔액은 움직이지만 달력·차트 같은 통계엔 **안 잡힌다** — 현금이 실제로 들어온 게 아니라 "평가액만 오른" 것이라서. `amount` 는 항상 양수고, 증감 방향은 `valuation_direction` 으로 표현한다.

### 3-4. category ↔ transaction 연결

| 방향 | 어떻게 | 비고 |
|---|---|---|
| transaction → category | `transaction.category_id` (논리 FK, nullable) | 이체·평가조정은 NULL |
| category → transaction | **코드 의존성 없음** | category 도메인은 transaction 을 import 하지 않음 (단방향) |
| 호출 방향 | transaction 의 `get_form_options`(service.py:244)·`list_transactions` 가 category 서비스를 호출 | category 가 거래에 종속되지 않음 |

> 카테고리를 지워도 거래는 살아있다(§4-6). 그래서 "죽은 카테고리"를 가리키는 거래가 생길 수 있고, 거래 조회 시엔 `find_by_ids`(필터 없는 조회)로 죽은 카테고리 이름까지 끌어와 표시한다.

---

## 4. 공통 메커니즘

카테고리·거래 API들이 공유하는 로직을 여기 모았다. §5 트레이스가 이 절들을 참조한다.

### 4-1. 거래 5종이 잔액·통계에 반영되는 규칙

§3-3 표가 요지다. 코드로 보면 두 군데서 이 분기가 일어난다:

**① 잔액용 — `sum_for_account` 의 종류별 합산**(§4-2 에서 상세)
**② 통계용 — 달력/차트 집계에서 종류 필터**
```python
# app/domain/transaction/repository.py:453  daily_sums_for_month — 달력 일별 집계
Transaction.tx_type != TxType.VALUATION   # 평가조정은 달력 수입/지출/이체 집계에서 제외
```
```python
# app/domain/transaction/repository.py:423  sum_by_type_for_month — 월 타입별 합계
elif tx_type in (TxType.EXPENSE, TxType.FIXED_EXPENSE):  # 고정지출도 "지출" 칸에 합산
    sums["expense"] += Decimal(total)
```

> 핵심 패턴: **FIXED_EXPENSE 는 어디서나 EXPENSE 와 한 묶음**, **VALUATION 은 어디서나 빠진다**(잔액 계산만 예외적으로 포함).

### 4-2. 거래합 — `sum_for_account` (03 §4-2가 받던 그 값)

03의 잔액 공식 `start_balance + income − expense − transfer_out + transfer_in + valuation_net` 에서 우변의 다섯 합계를 만드는 곳이 바로 여기다.

```python
# app/domain/transaction/repository.py:185  sum_for_account
# 한 통장이 낀(출금이든 입금이든) 거래를 종류·방향별로 GROUP BY 해서 한 번에 합산
.where(or_(Transaction.account_id == account_id,
           Transaction.to_account_id == account_id))   # 출금/입금 양쪽 다
.group_by(tx_type, account_id, to_account_id, valuation_direction)
```
그 다음 파이썬에서 통장 관점으로 **분배**한다:
```python
# app/domain/transaction/repository.py:225
if   tx_type == INCOME        and acc_id == account_id: sums["income"]       += total
elif tx_type in (EXPENSE, FIXED_EXPENSE) and acc_id == account_id: sums["expense"] += total
elif tx_type == TRANSFER:
    if acc_id    == account_id: sums["transfer_out"] += total   # 내가 출금 쪽
    if to_acc_id == account_id: sums["transfer_in"]  += total   # 내가 입금 쪽 ★같은 row, 다른 관점
elif tx_type == VALUATION and acc_id == account_id:
    sums["valuation_net"] += total if direction == INCREASE else -total
```

> **이체가 한 row 인데도 양쪽 통장 잔액이 맞는 비밀이 여기 있다**(§4-3). A→B 이체 1줄에서, A의 `sum_for_account` 는 `transfer_out` 에 더하고, B의 `sum_for_account` 는 같은 줄을 `transfer_in` 에 더한다. 한 줄이 두 통장에 다르게 잡힌다.

**단건 vs 배치 — 03 §4-2의 "공식 하나, 구현 둘"과 짝**
| 함수 | repo:line | 용도 | 반환 |
|---|---|---|---|
| `sum_for_account` | 185 | 단건(통장 1개), `to_date` 로 누적 기준점도 지원 | `dict[str, Decimal]` |
| `sum_for_accounts` | 246 | 배치(통장 N개), N+1 차단 | `dict[UUID, dict[str, Decimal]]` |

둘은 **동일한 분배 로직**(이체 양쪽 반영 포함)을 쓴다. 03의 목록 API가 부르던 게 `sum_for_accounts`, 단건이 부르던 게 `sum_for_account` 다.

### 4-3. 이체는 한 줄 — 양방향을 한 row 로

A→B 이체를 만들면 **레코드는 하나**다(출금/입금 두 줄 X):

```python
# app/domain/transaction/service.py:151  create_transaction
tx = Transaction(
    account_id    = req.account_id,                                       # 출금 통장 A
    to_account_id = req.to_account_id if req.tx_type == TRANSFER else None,  # 입금 통장 B
    amount        = req.amount,                                           # 양수
    ...
)
```

"이 통장 입장에서 +냐 −냐"는 **저장하지 않고 조회 때 계산**한다:
```python
# app/domain/transaction/service.py:422  _signed_amount
if tx_type == TRANSFER and tx.to_account_id == account_id: return  tx.amount   # 내가 받는 쪽 → +
if tx_type == INCOME:                                      return  tx.amount
if tx_type == VALUATION:  return tx.amount if INCREASE else -tx.amount
return -tx.amount   # EXPENSE / FIXED_EXPENSE / 이체 출금 → −
```

> **왜 한 줄인가?** 두 줄로 쪼개면 수정·삭제 시 둘을 항상 동기화해야 하고 틀어질 위험이 생긴다. 한 줄로 두고 "관점에 따라 부호를 계산"하면 진실은 언제나 하나(03의 "잔액은 저장 안 한다"와 같은 철학). 대가는 §4-2의 분배 로직 — 한 줄을 두 통장이 다르게 합산해야 한다는 점.

### 4-4. FK 소속 검증 — 논리 FK 의 대가

DB FK 가 없으니(§3-2) "이 통장/카테고리가 정말 내 가계부 것이냐"를 서비스가 직접 확인한다:

```python
# app/domain/transaction/service.py:349  _validate_fk_belong_to_household
accounts = await AccountRepository(db).find_by_ids(account_ids)
for a in accounts:
    if a.household_id != household_id or a.data_stat_cd != ACTIVE:   # 남의 것/삭제된 것 차단
        raise CustomException(ErrorCode.NOT_FOUND)
if tx_type == VALUATION:                       # 평가조정은 수동자산 통장에만
    if a.account_type not in MANUAL_ASSET_ACCOUNT_TYPES: raise BAD_REQUEST
elif tx_type not in (None, TRANSFER):          # 지출/수입은 수동자산 통장 금지
    if a.account_type in MANUAL_ASSET_ACCOUNT_TYPES: raise BAD_REQUEST
```

카테고리는 소속 + **종류 매칭**까지 본다:
```python
# app/domain/transaction/service.py:328  _category_kind_matches
EXPENSE / FIXED_EXPENSE 거래 → EXPENSE 카테고리만
INCOME  거래               → INCOME 카테고리만
TRANSFER                   → 카테고리 없음
```
> 종류가 어긋나면(예: 지출에 수입 카테고리) `BAD_REQUEST`. 이유는 코드 주석 그대로 — "월합계(타입 기준)와 카테고리차트(kind 기준)가 어긋나기" 때문(service.py:330).

스키마 단계에서도 1차로 거른다(서비스 검증과 이중 방어):
```python
# app/domain/transaction/schema.py:51  TransactionCreateRequest._validate
amount <= 0                                  → BAD_REQUEST
TRANSFER  : to_account_id 필수, account_id≠to_account_id, category·fixed 금지
FIXED_EXPENSE : fixed_expense_id 필수
VALUATION : valuation_direction 필수, category 금지
그 외     : to_account_id 금지
```

### 4-5. 러닝 밸런스 — 원장 각 줄에 "거래 직후 잔액" 붙이기

`GET /transaction/account/{id}/ledger` 는 통장 원장을 보여주며 **각 줄에 그 거래 직후 잔액(`balance_after`)** 을 단다. 거래는 최신순(desc)으로 내려오는데 잔액은 "기준점에서 역산"한다:

```python
# app/domain/transaction/service.py:498  _build_ledger_items
running = start_balance          # 첫 행(가장 최신) = 기준 시점까지의 누적 잔액
for r in rows:                   # 최신 → 과거 순
    signed = _signed_amount(r, account_id)
    item.balance_after = running # 이 거래 직후 잔액
    running -= signed            # 한 칸 과거로 내려가면 이 거래의 효과를 되돌림
```

기준점 `start_balance` 는 §4-2의 거래합으로 만든다:
```python
# app/domain/transaction/service.py:466  _ledger_start_balance
sums = await repo.sum_for_account(account.id, to_date=balance_to_date)  # 기준일까지 누적
return start_balance + income − expense − transfer_out + transfer_in + valuation_net
```

**페이지 경계는 커서에 `carry` 를 실어 잇는다:**
```python
# app/domain/transaction/service.py:437  _split_ledger_cursor
# ledger 커서 = "{tx_date}|{frst_reg_dt}|{id}|{carry_balance}"
#   앞 3개 = 정렬 커서(list_by_cursor 용), 맨 뒤 carry = 다음 페이지 첫 행의 시작 잔액
```
> **왜 역산인가?** 거래는 최신순으로 보여주는데(사용자 기대), 잔액은 본질적으로 "과거부터 누적"이다. 그래서 "현재 누적 잔액"을 기준점으로 잡고 위(최신)에서 아래(과거)로 내려가며 각 거래 효과를 빼나간다. 다음 페이지로 넘어갈 땐 마지막 줄의 `running` 을 커서에 실어 이어받는다 — 페이지마다 처음부터 다시 합산하지 않으려고.

> **주의:** ledger 의 러닝밸런스는 현금흐름/수동자산 통장에서만 정확하다. INVESTMENT 통장은 매매 현금이 거래 밖(포트폴리오, →06)이라 부정확 → 프론트가 잔액 표시를 숨긴다(service.py:103 주석).

### 4-6. 카테고리 삭제 = soft-delete만, 거래는 그대로 (orphan 허용)

```python
# app/domain/category/service.py:138  delete_category
# 차단 없이 soft-delete만 — 거래/고정비의 category_id 는 그대로 둔다
category.data_stat_cd = DataStatus.DELETED
```
- **거래를 건드리지 않는다.** "식비" 카테고리를 지워도 식비로 찍힌 과거 거래의 `category_id` 는 그대로 — 죽은 카테고리를 가리키는 "고아 거래"가 된다.
- **죽은 카테고리도 이름은 조회된다.** 거래 목록은 `find_by_ids`(상태 필터 없음, category/repository.py)로 죽은 카테고리 이름까지 끌어와 표시. 단 **새 거래 입력 선택지**(`find_active_by_household_id`)엔 안 나온다.

> 03의 **통장** 삭제는 자식 거래까지 cascade soft-delete 했다. 여기 **카테고리** 삭제는 정반대 — 자식을 안 건드린다. 대비해서 기억: 통장은 "돈의 그릇"이라 비우면 거래가 무의미하지만, 카테고리는 "꼬리표"라 떼도 거래 자체는 유효하다.

### 4-7. 커서 페이징 (거래 목록)

03 §4-3의 통장 커서와 같은 원리, 키만 다르다. 거래는 **3-튜플 복합 커서**:
```python
# app/domain/transaction/repository.py:76  _cursor_after / :113 order_by
order_by(tx_date DESC, frst_reg_dt DESC, id DESC)   # 거래일 → 등록시각 → id
# 커서 = "{tx_date}|{frst_reg_dt}|{id}"
.limit(limit + 1)                                    # 1개 더 가져와 has_next 판정
```
> 통장은 `frst_reg_dt|id` 2-튜플이었는데 거래는 `tx_date` 가 먼저다 — 사용자는 "거래가 일어난 날" 순으로 보고 싶지 "DB에 등록된 시각" 순이 아니라서. 같은 날 거래는 `frst_reg_dt` → `id` 로 tie-break.

---

## 5. 엔드포인트별 풀 트레이스

전부 `CurrentHousehold` 를 받는다(→02 §4): 로그인 + 그 가계부 멤버여야 진입. 실제 URL은 `root_path="/api"` + prefix → 예: `GET /api/transaction/list`.

### 5-A. 카테고리 (`/category`) — 5개

#### GET /category/list — 카테고리 목록 (무한 스크롤)
```
요청  GET /api/category/list?limit=30&searchTerm=&kind=&isArchived=   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:22  list_categories
      household: CurrentHousehold (멤버십)
      q: CategoryListQuery(Query) → limit 1~200(schema.py:14), kind enum 파싱
─[2] 서비스        service.py:41  list_categories_cursor
      repo.list_by_cursor → frst_reg_dt DESC, limit+1 (관리 페이지용 최신순)
      count_search → total_count
      next_cursor = "{마지막.frst_reg_dt}|{id}",  has_next = len>limit
─[3] 응답 조립     service.py:63  _build_response × N → CategoryResponse (kind 문자열→enum)
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(CursorPage[CategoryResponse])
```
> 내부용 `list_categories`(service.py:22)는 별도 — `kind/sort_order` 정렬로 폼 옵션(거래 입력 화면)에 쓴다. 외부 API(`/list`)는 관리 페이지용이라 최신순 커서.

#### POST /category/create — 카테고리 생성
```
요청  POST /api/category/create  {kind, name, color?, icon?, sortOrder?}  + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:40  household: CurrentHousehold
      CategoryCreateRequest._validate(schema.py:27): name 1~100자, color ≤7자, 아니면 BAD_REQUEST
─[2] 서비스        service.py:85  create_category
      sort_order = req.sort_order ?? (repo.max_sort_order(household.id, kind)+1)  ← 같은 kind 내 MAX+1
      Category(... is_archived=False, data_stat_cd=ACTIVE) → repo.save → add+flush
─[3] 응답 조립     service.py:110  _build_response → CategoryResponse
─[4] 트랜잭션 종료  get_db — commit (INSERT 확정)
응답  ApiResponse.ok(CategoryResponse)
```

#### GET /category/detail/{category_id} — 단건
```
요청  GET /api/category/detail/{id}   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:51  household: CurrentHousehold
─[2] 서비스        service.py:154  get_category_detail
      repo.find_by_id (ACTIVE만) → 없거나 / household_id 불일치 / 비활성 → NOT_FOUND
─[3] 응답 조립     service.py:162  _build_response
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(CategoryResponse)
```

#### PUT /category/update/{category_id} — 수정 (보관 토글 포함)
```
요청  PUT /api/category/update/{id}  {kind?, name?, color?, icon?, sortOrder?, isArchived?}  + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:62  household: CurrentHousehold
      CategoryUpdateRequest._validate(schema.py:44): name 주면 1~100, color 주면 ≤7
─[2] 서비스        service.py:113  update_category
      find_by_id + household_id 일치 가드 → NOT_FOUND
      None 아닌 필드만 부분 수정 (is_archived 포함 → 보관/해제 토글)
      db.flush
─[3] 응답 조립     service.py:135  _build_response (수정 후 최신)
─[4] 트랜잭션 종료  get_db — commit (UPDATE 확정)
응답  ApiResponse.ok(CategoryResponse)
```

#### DELETE /category/delete/{category_id} — soft-delete (거래 보존)
```
요청  DELETE /api/category/delete/{id}   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:74  household: CurrentHousehold
─[2] 서비스        service.py:138  delete_category
      find_by_id + household_id 일치 가드 → NOT_FOUND
      data_stat_cd = DELETED 만 — 거래의 category_id 는 손대지 않음          → §4-6 (orphan 허용)
─[3] 응답 조립     반환값 없음 (None)
─[4] 트랜잭션 종료  get_db — commit
응답  ApiResponse.ok()
```

### 5-B. 거래 (`/transaction`) — 8개

#### GET /transaction/list — 거래 목록 (무한 스크롤)
```
요청  GET /api/transaction/list?limit=20&cursor=&txType=&accountId=&categoryId=&year=&month=&fromDate=&toDate=
      + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:27  list_transactions
      household: CurrentHousehold
      q: TransactionListQuery(Query) → limit 1~500(schema.py), 필터 추출 → TransactionFilter
      ※ cursor+limit 을 같은 모델에 둔 이유 = FastAPI Query unwrap 버그 회피(schema.py 주석)
─[2] 서비스        service.py:40  list_transactions
      repo.list_by_cursor (repository.py:99) → tx_date DESC, limit+1                → §4-7
      repo.count → total
      account/category batch 조회 (find_by_ids) → account_map / category_map         (N+1 차단)
      next_cursor = "{tx_date}|{frst_reg_dt}|{id}",  has_next = len>limit
─[3] 응답 조립     service.py:64  _build_response × N → TransactionResponse(통장명·카테고리명/색/아이콘 조인)
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(CursorPage[TransactionResponse])
```

#### POST /transaction/create — 거래 생성
```
요청  POST /api/transaction/create  {txType, amount, txDate, accountId, toAccountId?, categoryId?,
       fixedExpenseId?, valuationDirection?, memo?}   + Bearer + X-Household-Id + CurrentUser
─[1] 의존성·검증   router.py:40  create_transaction
      household: CurrentHousehold, current_user: CurrentUser (paid_by 기본값용)
      TransactionCreateRequest._validate(schema.py:51): 종류별 필수/금지 필드 + amount>0   → §4-4
─[2] 서비스        service.py:136  create_transaction
      _validate_fk_belong_to_household: 통장·카테고리 소속 + 수동자산 제약 + kind 매칭     → §4-4
      _validate_fixed_belongs: fixed_expense_id 소속 검증
      Transaction(...) — TRANSFER 아니면 to_account_id=None, VALUATION이면 direction 저장   → §4-3
      paid_by_user_id = req값 ?? current_user.id
      repo.save → add+flush (id 채워짐)
─[3] 응답 조립     service.py:171  _single_response → 통장·카테고리 조인 → TransactionResponse
─[4] 트랜잭션 종료  get_db — commit (INSERT 확정) → 통장 잔액은 다음 조회 때 이 거래까지 합산됨   → §4-2
응답  ApiResponse.ok(TransactionResponse)
```

#### PUT /transaction/update/{tx_id} — 수정 (부분)
```
요청  PUT /api/transaction/update/{id}  {위 필드 전부 optional}   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:52  household: CurrentHousehold
      TransactionUpdateRequest._validate(schema.py): amount 주면 >0, account≠to_account
─[2] 서비스        service.py:174  update_transaction
      find_by_id + household_id 가드 → NOT_FOUND
      _validate_update_fks: 변경 후 값 기준 FK 재검증                              → §4-4
      _apply_partial_update: None 아닌 필드만 병합 (_TX_UPDATABLE_FIELDS, service.py:321)
      _normalize_to_account: TRANSFER 아니게 바뀌면 to_account_id=None            ★타입전환 시 가짜이체 방지
      _validate_transfer_consistency: TRANSFER면 to_account 필수·출발≠도착
      db.flush
─[3] 응답 조립     service.py:191  _single_response → TransactionResponse
─[4] 트랜잭션 종료  get_db — commit (UPDATE 확정)
응답  ApiResponse.ok(TransactionResponse)
```
> `_normalize_to_account`(service.py:559)가 미묘하다 — 이체를 지출로 바꾸면 옛 `to_account_id` 가 남아 상대 통장 원장에 "유령 입금"이 잡힐 수 있다. 그래서 TRANSFER 가 아니게 되는 순간 도착 통장을 지운다.

#### DELETE /transaction/delete/{tx_id} — soft-delete
```
요청  DELETE /api/transaction/delete/{id}   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:64  household: CurrentHousehold
─[2] 서비스        service.py:194  delete_transaction
      find_by_id + household_id 가드 → NOT_FOUND
      data_stat_cd = DELETED → db.flush                  (이체도 한 row라 한 번에 양쪽서 사라짐)
─[3] 응답 조립     반환값 없음 (None)
─[4] 트랜잭션 종료  get_db — commit
응답  ApiResponse.ok()
```
> 이체가 한 줄(§4-3)이라 삭제도 한 번. 두 줄이었다면 둘 다 지워야 했을 것. 단 03의 **통장** 삭제 시엔 이체를 "상대가 살았나" 따져 선별 삭제했다(03 §4-4) — 거기선 통장 단위라 양쪽을 구분해야 했기 때문.

#### GET /transaction/detail/{tx_id} — 단건
```
요청  GET /api/transaction/detail/{id}   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:75  household: CurrentHousehold
─[2] 서비스        service.py:207  get_transaction_detail
      find_by_id → 없거나 / household_id 불일치 / 비활성 → NOT_FOUND
─[3] 응답 조립     service.py:215  _single_response → 통장·카테고리 조인 → TransactionResponse
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(TransactionResponse)
```

#### GET /transaction/account/{account_id}/ledger — 통장 원장 (러닝 밸런스)
```
요청  GET /api/transaction/account/{id}/ledger?limit=20&cursor=&year=&month=   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:86  get_account_ledger
      household: CurrentHousehold, limit 1~500, year 2000~2100, month 1~12
─[2] 서비스        service.py:81  list_account_ledger
      AccountRepository.find_by_id + household_id 가드 → NOT_FOUND
      _split_ledger_cursor → (정렬커서, carry)                                   → §4-5
      _ledger_filter → year+month면 그달+기준일=말일, 아니면 전체
      repo.list_by_cursor (limit+1) + repo.count
      _ledger_start_balance → carry 있으면 그 값, 없으면 sum_for_account 로 기준잔액  → §4-2·§4-5
      _build_ledger_items → 각 줄 signed_amount + balance_after 역산              → §4-5
      next_cursor = "{tx_date}|{frst_reg_dt}|{id}|{running}"  (carry 실어 다음 페이지로)
─[3] 응답 조립     service.py:128  AccountLedgerPage(items[signed_amount·balance_after 포함])
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(AccountLedgerPage)
```

#### GET /transaction/calendar/{year}/{month}/full — 달력 1호출 (집계+거래)
```
요청  GET /api/transaction/calendar/2026/6/full   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:107  year 2000~2100, month 1~12  + CurrentHousehold
─[2] 서비스        service.py:218  get_calendar_full  (세 조회를 한 응답으로 합침)
      get_calendar (service.py:266) → daily_sums_for_month (repository.py:433, VALUATION 제외) → 일별 합계  → §4-1
      stats_service.get_monthly_stats → 카테고리별 집계 (→08 stats)
      list_transactions(limit=500) → 그달 거래 전부 (한 달 평균 100건 미만이라 커서 불필요)
─[3] 응답 조립     service.py:232  CalendarFullResponse(월합계 + days[] + by_category[] + transactions[])
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(CalendarFullResponse)
```
> 달력 화면이 필요한 모든 데이터(일별 점·카테고리 차트·거래 리스트)를 **한 번에** 내려 라운드트립을 줄인다. 일별 집계에서 평가조정은 빠진다(§4-1).

#### GET /transaction/form-options — 거래 입력 폼 옵션
```
요청  GET /api/transaction/form-options   + Bearer + X-Household-Id
─[1] 의존성·검증   router.py:119  household: CurrentHousehold
─[2] 서비스        service.py:244  get_form_options  (세 도메인 서비스를 모음 — 순환 import 회피 위해 함수 내 import)
      account_service.list_accounts        → 통장 선택지
      category_service.list_categories     → 카테고리 선택지 (kind/sort_order 정렬, 활성만)
      fixed_service.list_fixed_expenses(is_archived=False) → 고정지출 선택지 (→05)
─[3] 응답 조립     service.py:259  TransactionFormOptionsResponse(accounts + categories + fixed_expenses)
─[4] 트랜잭션 종료  get_db — 조회뿐, 정상 종료
응답  ApiResponse.ok(TransactionFormOptionsResponse)
```

---

## 6. 데이터 흐름 (도메인 큰 그림)

```
프론트 ──Bearer + X-Household-Id──▶ /category/* · /transaction/*
                                       │
                  CurrentHousehold ── 멤버십 검증 (아니면 HH001)
                                       │
        ┌──────────────────────────────┼────────────────────────────────┐
   거래 생성/수정                    조회                              삭제
        │                              │                               │
   FK·종류 검증(§4-4)            list/detail/ledger/calendar      거래: soft-delete (한 row)
   종류별 필드 정규화(§4-3)       거래합 sum_for_account(§4-2)      카테고리: soft-delete, 거래 보존(§4-6)
   INSERT/UPDATE + flush         러닝밸런스 역산(§4-5)
        │                              │                               │
        └──────────── get_db: 성공 commit / 예외 rollback ──────────────┘
                                       │
                            ApiResponse 봉투로 응답
                                       │
              ┌────────────────────────┴────────────────────────┐
        통장 잔액(03)                              월간 스냅샷 박제(05) / 통계(08)
   sum_for_account 가 거래합 제공            sum_by_*_for_month 가 월 집계 제공
```

> 거래는 **소비처가 많다**: 통장 잔액(03)·월간 스냅샷(05)·달력/통계(08)·포트폴리오 현금흐름(06)이 전부 이 테이블의 합계를 읽는다. 거래 테이블이 이 앱의 "원장(ledger)" 그 자체.

---

## 7. 이 문서에서 꼭 기억할 규칙

1. **거래 5종이 규칙의 전부.** EXPENSE·INCOME·TRANSFER·FIXED_EXPENSE·VALUATION — 종류마다 필수 필드·잔액 반영·통계 포함이 다르다(§3-3, §4-1). FIXED_EXPENSE=지출과 한 묶음, VALUATION=통계 제외.
2. **이체는 한 줄**(§4-3). `account_id`(출금)·`to_account_id`(입금)을 가진 단일 row, 부호는 조회 때 `_signed_amount` 로 계산. 같은 줄을 §4-2 분배가 두 통장에 다르게 합산해 양쪽 잔액이 맞는다.
3. **거래합(`sum_for_account`)이 03 잔액 공식의 입력**(§4-2). `income/expense/transfer_in/transfer_out/valuation_net` 5칸 — 03에서 "이미 합산됐다"던 그 값.
4. **실제 FK 는 `fixed_expense_id` 하나뿐**(§3-2). 나머지는 논리 FK → 소속·종류 검증을 서비스가 직접(§4-4).
5. **카테고리 삭제는 거래를 안 건드린다**(§4-6, orphan 허용). 통장 삭제(cascade)와 정반대. 죽은 카테고리도 거래 표시용 이름은 조회됨.
6. **러닝 밸런스는 역산**(§4-5). 최신순 원장에 거래 직후 잔액을 붙이려 "현재 누적"을 기준점으로 위→아래로 효과를 빼나가고, 페이지 경계는 `carry` 를 커서에 실어 잇는다.
7. 모든 API는 `CurrentHousehold` + `household_id` 일치 검사 → 남의 가계부 거래/카테고리 접근 불가.

---

## 다음 문서
➡ **`05-fixed-snapshot.md`** — 거래에 매달리는 **고정지출(FixedExpense)** 메타와, 매월 1일 스케줄러가 통장 잔액·월 수입/지출을 박제하는 **월간 스냅샷(AccountSnapshot)**. 03 §4-5의 "지난 달은 박제 스냅샷에서 읽는다"와 §4-1의 FIXED_EXPENSE 가 여기서 완결된다.
