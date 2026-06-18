# 00. 전체 그림 — 이 백엔드를 처음 여는 사람을 위한 지도

> 이 문서 시리즈(`docs/codewalk/`)는 **FastAPI를 처음 보는 주니어 개발자**가 이 코드베이스를 혼자 읽어나갈 수 있게 만든 "코드 산책 가이드"야. 00번은 그 출발점 — 숲을 먼저 보고, 그다음 문서들에서 나무를 본다.

---

## 1. 이게 뭐 하는 프로젝트야?

**부부가 함께 쓰는 가계부 앱의 백엔드(서버)** 야.

- 부부 두 사람이 **하나의 가계부(household, "세대")** 를 공유한다.
- 통장(account)·거래내역(transaction)·카테고리·고정지출·투자 포트폴리오까지 관리한다.
- 프론트(웹/앱)가 HTTP로 요청을 보내면, 이 백엔드가 DB를 읽고/쓰고 **JSON으로 응답**한다.

즉 이 코드의 역할은 한 줄로:

> **HTTP 요청을 받아 → 검증하고 → DB를 다루고 → 일관된 JSON으로 돌려주는 것.**

---

## 2. 기술 스택 한눈에

| 항목 | 사용 기술 | 한마디 |
|---|---|---|
| 언어 | Python 3.14 | 타입 힌트 적극 사용 |
| 웹 프레임워크 | **FastAPI** | 라우팅 + 검증 + 문서화 자동 |
| 실행기(ASGI 서버) | uvicorn | 실제로 앱을 띄우는 프로그램 |
| DB | PostgreSQL | 관계형 DB |
| DB 라이브러리(ORM) | **SQLAlchemy 2.x (async)** + asyncpg | 파이썬 객체 ↔ 테이블 매핑 |
| 마이그레이션 | Alembic | 테이블 구조 변경 이력 관리 (`alembic/versions/` 22개) |
| 인증 | JWT (`python-jose`) + bcrypt | 토큰 기반 로그인 |
| 패키지 매니저 | uv | `uv sync`, `uv run ...` |

처음이라면 이 정도만 기억하면 돼: **FastAPI로 API를 만들고, SQLAlchemy로 DB를 다루고, 둘 다 `async`(비동기)로 돈다.**

---

## 3. 레이어드 아키텍처 — 코드가 4층으로 쌓여 있다

이 프로젝트의 모든 도메인(통장, 거래 등)은 **똑같은 4층 구조**를 반복한다. 이걸 이해하면 17개 도메인이 다 똑같이 읽힌다.

```
┌─────────────────────────────────────────────────────────┐
│  router.py    "어떤 URL이 들어오면 뭘 호출할지" (입구)        │
│      ↓ 호출                                                │
│  service.py   "실제 규칙/계산/판단" (두뇌 — 비즈니스 로직)     │
│      ↓ 호출                                                │
│  repository.py "DB에 SELECT/INSERT/UPDATE" (손발 — DB 접근) │
│      ↓ 다룸                                                │
│  model.py     "테이블 한 개 = 클래스 한 개" (DB 테이블 정의)   │
└─────────────────────────────────────────────────────────┘
   곁들이: schema.py(요청/응답 모양), enum.py(상수 종류)
```

| 파일 | 책임 | 하면 안 되는 것 |
|---|---|---|
| `router.py` | URL·HTTP메서드 정의, 요청 받기, 응답 포장 | ❌ 여기서 직접 DB 쿼리 |
| `service.py` | 비즈니스 규칙, 계산, 검증, 트랜잭션 단위 | ❌ HTTP 세부(상태코드 일일이) 신경 |
| `repository.py` | DB 조회/저장만 | ❌ 비즈니스 판단 |
| `model.py` | 테이블 컬럼 정의 | — |
| `schema.py` | 입력/출력 JSON의 모양(Pydantic) | — |

> **왜 나누나?** 각 층이 한 가지만 하면, 버그를 찾을 때 "어느 층 문제인지"가 바로 좁혀진다. 잔액 계산이 틀리면 service, 응답 필드가 이상하면 schema, 쿼리가 느리면 repository.

---

## 4. 요청 하나의 생애주기 (가장 중요!)

프론트가 `POST /api/transaction/create` 를 부르면 서버 안에서 이런 순서로 흐른다:

```
1. uvicorn 이 HTTP 요청 수신
2. CORS 미들웨어        → 허용된 출처인가?
3. AccessLogMiddleware  → "POST /transaction/create ... 45ms" 로그 한 줄
4. IdempotencyMiddleware→ (POST면) 같은 요청 중복인가? 캐시 있으면 즉시 반환
5. router.py            → 이 URL에 매칭되는 함수 실행
6. Depends(...)         → 필요한 것 주입: DB세션, 로그인 유저, 현재 세대
7. service.py           → 규칙 적용 + 계산
8. repository.py        → DB에 INSERT/UPDATE
9. get_db 가 자동 commit (예외 났으면 자동 rollback)
10. ApiResponse 로 포장 → {status, code, message, data} JSON 반환
```

이 10단계가 **모든 요청의 뼈대**다. 4·6·9번이 이 프로젝트의 특징적인 부분이고, 전부 `01-core-infra.md` 에서 자세히 다룬다.

---

## 5. FastAPI 입문 — 딱 4개 개념만

이 코드를 읽으려면 FastAPI의 핵심 4가지만 알면 된다.

### (1) APIRouter — URL 묶음
```python
# app/domain/health/router.py 같은 패턴
router = APIRouter(prefix="/health", tags=["health"])

@router.get("/")          # GET /health/ 요청이 오면
async def health():        # 이 함수가 실행된다
    return ApiResponse.ok()
```
`@router.get` / `@router.post` 위에 붙은 데코레이터가 "이 URL = 이 함수" 를 연결한다.

### (2) Depends — 의존성 주입 ("필요한 걸 알아서 넣어줘")
```python
async def create(db: AsyncSession = Depends(get_db)):
    # ↑ FastAPI 가 get_db() 를 실행해서 db 를 자동으로 채워준다
    ...
```
함수 인자에 `Depends(X)` 를 쓰면, FastAPI가 X를 먼저 실행해 그 결과를 넣어준다. **DB세션, 로그인 유저, 현재 세대**가 전부 이 방식으로 들어온다. (➡ `01` 문서 핵심)

### (3) Pydantic — 입력/출력의 "모양"을 클래스로
```python
class UserCreate(CamelBaseModel):
    email: str
    name: str
```
요청 JSON이 이 모양과 안 맞으면 FastAPI가 **자동으로 검증 에러**를 낸다. 코드에서 `if not email...` 같은 수동 검증을 줄여준다.

### (4) async / await — 비동기
```python
async def find_user(...):
    user = await repo.find_by_id(...)   # DB 기다리는 동안 다른 요청 처리 가능
```
DB·네트워크처럼 "기다리는" 작업은 `await` 로 호출한다. 그동안 서버는 멈추지 않고 다른 요청을 처리한다. **이 프로젝트는 거의 모든 함수가 `async`** 다.

> ❌ `def get_user(...)` (동기) → ✅ `async def get_user(...)` 로 일관.

---

## 6. 이 프로젝트만의 공통 규약 (도메인마다 반복됨)

문서를 읽다 보면 계속 마주칠 약속들. 미리 알아두면 편하다.

| 규약 | 내용 | 어디서 |
|---|---|---|
| **응답 봉투** | 모든 응답은 `{status, code, message, data}` 형태 (`ApiResponse`) | `core/api_response.py` |
| **에러 처리** | 비즈니스 오류는 `raise CustomException(ErrorCode.X)` → 핸들러가 위 봉투로 변환 | `core/exceptions/` |
| **공통 컬럼** | 모든 테이블에 `id`(UUID) · `frst_reg_dt`(생성) · `last_mdfcn_dt`(수정) · `data_stat_cd`(상태) | `core/model.py` BaseEntity |
| **Soft Delete** | 진짜 DELETE 안 함. `data_stat_cd = "99"`(삭제) / `"50"`(활성) | `core/enums/data_status.py` |
| **ID** | 자동증가 숫자 X → **UUID** 사용 | BaseEntity |
| **JSON 네이밍** | DB·파이썬은 `snake_case`, 응답 JSON은 자동으로 `camelCase` | `core/schema.py` |
| **URL prefix** | 앱에 `root_path="/api"` → 라우터 `/transaction` 은 실제로 **`/api/transaction`** | `main.py:48` |
| **트랜잭션** | `get_db` 가 요청 끝에 자동 commit/rollback. 서비스는 보통 `flush()` 만 | `core/database.py` |

### root_path 함정 (입문자가 꼭 헷갈림)
```python
# main.py
app = FastAPI(root_path="/api")          # ← 모든 경로 앞에 /api

# router.py
router = APIRouter(prefix="/transaction") # ← 코드엔 /api 안 보임

# 실제 호출 URL = /api/transaction/...    ← prefix + root_path 합쳐짐
```
코드에는 `/api` 가 안 적혀 있는데 실제 URL엔 붙는다. 이걸 모르면 "왜 404지?" 하게 된다.

---

## 7. 디렉토리 지도

```
app/
├ main.py              앱 생성 + 미들웨어/라우터 등록 + 시작·종료 훅 (← 모든 것의 입구)
├ core/                도메인 공통 토대 (➡ 01 문서)
│  ├ database.py        get_db, 엔진/세션
│  ├ model.py           BaseEntity (공통 컬럼)
│  ├ api_response.py    ApiResponse 봉투
│  ├ exceptions/        CustomException + ErrorCode + 핸들러
│  ├ auth/              JWT, 비밀번호 해싱, CurrentUser
│  ├ idempotency/       POST 중복요청 방지 미들웨어
│  ├ scheduler.py·jobs.py  정기 작업 5개 (환율/시세/정리/스냅샷)
│  └ pagination.py, dates.py, types.py, schema.py, enums/
└ domain/              17개 업무 도메인 (각자 4층 구조)
   ├ user, auth, household           인증·세대        (➡ 02)
   ├ account                          계좌            (➡ 03)
   ├ category, transaction            카테고리·거래    (➡ 04)
   ├ fixed, account_snapshot          고정지출·스냅샷  (➡ 05)
   ├ portfolio                        투자 매매        (➡ 06)
   ├ market_price, exchange_rate, wealth  시세·환율·순자산 (➡ 07)
   └ home, stats, settings, enum, health  대시보드·통계·기타 (➡ 08)
```

> 도메인 폴더 중 `market_price`, `exchange_rate` 는 **URL이 없는 내부용**이다(라우터 미등록). 스케줄러와 portfolio가 내부에서 호출한다. ➡ 자세한 건 07 문서.

---

## 8. 이 문서에서 꼭 기억할 것

1. **모든 도메인은 router → service → repository → model 4층** 구조다. 하나 이해하면 다 똑같다.
2. **요청 1개 = 10단계 생애주기.** 특히 미들웨어(멱등성) → Depends(주입) → get_db(자동 commit) 가 이 프로젝트의 색깔.
3. **응답은 항상 `ApiResponse` 봉투, 에러는 `CustomException`.**
4. **삭제는 진짜 삭제가 아니라 `data_stat_cd="99"`** (soft delete).
5. **실제 URL = `/api` + 라우터 prefix.**

---

## 다음 문서

➡ **`01-core-infra.md`** — 위에서 계속 나온 `get_db` / `BaseEntity` / `ApiResponse` / `CustomException` / 멱등성 / 스케줄러의 실제 코드를 연다. 도메인을 읽기 전에 이 토대를 먼저 잡는 게 빠르다.
