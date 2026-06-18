# 01. core — 모든 도메인이 깔고 앉는 공통 토대

> `app/core/` 는 특정 업무(통장·거래…)에 속하지 않는 **공통 인프라**다. 도메인 17개가 전부 여기 있는 도구를 가져다 쓴다. 그래서 도메인을 읽기 전에 여기를 먼저 잡으면, 나머지가 훨씬 빨리 읽힌다.

> 이 문서는 코드 인용이 좀 많다. 전부 외울 필요 없고, **"이런 게 있고 어디 있는지"** 만 잡으면 된다. 나중에 도메인 문서에서 다시 불러줄 거야.

---

## 들어가기 전: 알아둘 개념 2개

| 개념 | 한마디 |
|---|---|
| **의존성 주입(Depends)** | 함수가 필요로 하는 것(DB세션, 로그인 유저)을 FastAPI가 알아서 만들어 넣어줌 |
| **미들웨어(Middleware)** | 라우터에 닿기 *전/후* 로 모든 요청이 거쳐가는 공통 관문 (로깅, 멱등성 등) |

---

## 1. database.py — DB 세션과 "트랜잭션 경계"

이 프로젝트에서 **가장 중요한 한 함수**가 여기 있다: `get_db`.

```python
# app/core/database.py:46
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """DB 세션 의존성"""
    async with async_session() as session:
        try:
            yield session              # (1) 라우터/서비스에 세션을 넘겨준다
            await session.commit()     # (2) 요청이 무사히 끝나면 → 자동 커밋
        except Exception:
            await session.rollback()   # (3) 도중에 예외가 터지면 → 자동 롤백
            raise                      # (4) 예외는 다시 위로 던진다 (핸들러가 잡음)
```

**이게 왜 핵심이냐:**

```
요청 시작 ── yield ──▶ [라우터→서비스→repository 가 session 사용] ──▶ 요청 끝
                                                                    │
                              예외 없음 → commit  ◀────────────────┘
                              예외 있음 → rollback
```

- 서비스 코드는 **`commit()` 을 직접 안 한다.** 보통 `session.flush()`(임시 반영, ID 채우기)만 하고, 진짜 저장(commit)은 `get_db`가 요청 끝에 한 번에 한다.
- 그래서 **한 요청 = 한 트랜잭션** 이 자연스럽게 보장된다. 중간에 에러 나면 그 요청이 건드린 게 통째로 rollback.

> ✅ 기억: **트랜잭션 경계 = get_db.** 서비스에서 commit 찾지 마라, 없다.

엔진/세션 설정도 같은 파일에 있다:
```python
engine = create_async_engine(settings.DATABASE_URL, pool_size=..., echo=settings.DEBUG)
async_session = async_sessionmaker(engine, expire_on_commit=False)
#                                          ↑ commit 후에도 객체 필드 접근 가능 (응답 직렬화 때 필요)
```
`init_db()`(시작 시 연결 확인) / `close_db()`(종료 시 정리)는 `main.py` 의 lifespan에서 호출된다.

---

## 2. model.py — 모든 테이블의 공통 부모 `BaseEntity`

```python
# app/core/model.py:13
class BaseEntity(Base):
    """공통 컬럼을 가진 추상 엔티티"""
    __abstract__ = True   # ← 이 클래스 자체는 테이블이 아님. 상속용 틀.

    id:            Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    frst_reg_dt:   Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=datetime.now)
    last_mdfcn_dt: Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=datetime.now,
                                                     onupdate=datetime.now)   # ← UPDATE 때 자동 갱신
    data_stat_cd:  Mapped[str]       = mapped_column(String(30))
```

도메인 모델(예: `User`, `Account`)은 전부 `BaseEntity` 를 상속하므로, **아래 4개 컬럼을 공짜로 얻는다.**

| 컬럼 | 의미 | 포인트 |
|---|---|---|
| `id` | 기본키 | 숫자 자동증가가 아니라 **UUID** (`uuid.uuid4`) |
| `frst_reg_dt` | 최초 등록 일시 | 감사(audit) 필드 |
| `last_mdfcn_dt` | 마지막 수정 일시 | `onupdate` 로 UPDATE 시 **자동** 갱신 |
| `data_stat_cd` | 데이터 상태 | soft delete용 ("50"=활성, "99"=삭제) |

> **논리 FK 주의:** 이 프로젝트의 모델들은 SQLAlchemy `relationship()` 을 **거의 안 쓴다**(전 도메인에서 0개, transaction만 물리 `ForeignKey` 2개). 즉 `user.households` 처럼 객체로 타고 들어가는 대신, **서비스가 `household_id` 로 직접 조회하고 검증**한다. 입문자가 "왜 관계 설정이 없지?" 하고 헷갈리는 지점 — 의도된 설계다.

---

## 3. config.py — 설정은 한 곳에서 (`settings`)

`pydantic-settings` 로 `.env` 파일을 읽어 `settings` 객체 하나에 모은다.

| 설정 | 기본/특징 |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` (필수) |
| `JWT_SECRET` | **32자 미만이면 부팅 실패** (검증 있음) |
| `JWT_EXPIRATION` / `JWT_REFRESH_EXPIRATION` | 1800초(30분) / 604800초(7일) |
| `JWT_ALGORITHM` | `HS256` |
| `DEBUG` | True면 SQL 로그 출력 |
| `ALLOWED_ORIGINS` | CORS 허용 출처 |
| `COOKIE_SECURE` | refresh 쿠키 HTTPS 전용 여부 |

쓸 때는 그냥 `from app.core.config import settings` → `settings.JWT_SECRET`.

---

## 4. api_response.py — 응답 봉투 `ApiResponse`

```python
# app/core/api_response.py:8
class ApiResponse(CamelBaseModel, Generic[T]):
    status: int
    code: str | None = None
    message: str | None = None
    data: T | None = None

    @classmethod
    def ok(cls, data=None):                       # 성공
        return cls(status=200, code="CM000", message="성공", data=data)

    @classmethod
    def fail(cls, status, code, message):          # 실패
        return cls(status=status, code=code, message=message)
```

**모든 응답이 이 4칸 봉투** 를 쓴다. 프론트는 항상 같은 모양을 받으니 처리 코드가 단순해진다.

```json
{ "status": 200, "code": "CM000", "message": "성공", "data": { ... } }
```

라우터는 보통 마지막에 `return ApiResponse.ok(data=...)` 로 끝난다. 실패(`fail`)는 직접 부를 일이 드물고, 대부분 **예외 핸들러가 자동으로** 만들어준다(다음 섹션).

---

## 5. exceptions/ — 에러를 일관되게 (CustomException → ErrorCode → 핸들러)

### 흐름
```
서비스에서  raise CustomException(ErrorCode.HOUSEHOLD_NOT_MEMBER)
                          │
        등록된 핸들러가 가로챔 (main.py 의 register_exception_handlers)
                          │
        ErrorCode 에서 status/code/message 꺼내 → ApiResponse.fail 로 변환 → JSON 응답
```

### ErrorCode = (status, code, message) 묶음 enum
```python
class ErrorCode(Enum):
    SUCCESS          = (200, "CM000", "성공")
    BAD_REQUEST      = (400, "CM001", "잘못된 요청입니다.")
    UNAUTHORIZED     = (401, "CM002", "인증이 필요합니다.")
    ...
    HOUSEHOLD_NOT_MEMBER = (403, "HH001", "가계부 멤버가 아닙니다.")
```

코드 접두사로 도메인을 구분한다:

| 접두사 | 영역 | 예 |
|---|---|---|
| `CM` | 공통 | CM004 데이터 없음, CM999 서버오류 |
| `AU` | 인증 | AU002 만료된 토큰 |
| `US` | 사용자 | US001 아이디 중복 |
| `HH` | 가계부/세대 | HH001 멤버 아님 |
| `PT` / `AC` | 포트폴리오 / 통장 | PT002 보유 중 삭제 불가 |
| `ID` | 멱등성 | ID003 처리 중 |

### 등록되는 핸들러 4종 (`handlers.py`)
| 잡는 예외 | 응답 |
|---|---|
| `CustomException` | error_code의 status/code/message 그대로 |
| `StarletteHTTPException` (404·405 등) | status를 표준 ErrorCode로 매핑, 한국어 메시지 |
| `RequestValidationError` (Pydantic 검증 실패) | 400 CM001 (영문 상세는 로그만) |
| `Exception` (그 외 전부) | 500 CM999 + traceback 로그 |

> ✅ 기억: **서비스에서는 그냥 `raise CustomException(ErrorCode.X)`.** HTTP 상태코드를 일일이 신경 안 써도, 핸들러가 알아서 일관된 봉투로 바꿔준다.

---

## 6. auth/ — 로그인의 토대 (JWT · 비밀번호 · CurrentUser)

> 회원가입/로그인 *흐름* 은 02 문서. 여기선 그 흐름이 쓰는 **도구**만.

### jwt.py — 토큰 만들고 풀기
```python
create_access_token(...)   # payload에 {"sub": user_id, "type": "access", "exp": ...} 넣고 서명
create_refresh_token(...)  # type="refresh", 만료 더 김(7일)
decode_token(token)        # 서명·만료 검증하고 payload 반환 (틀리면 예외)
```
- `sub` = 사용자 UUID, `type` = access/refresh 구분, `exp` = 만료시각.

### security.py — 비밀번호 해싱 (bcrypt)
```python
await hash_password(pw)            # bcrypt 해시 (asyncio.to_thread 로 별도 스레드 — 이벤트 루프 안 막음)
await verify_password(pw, hashed)  # 비교
```
> bcrypt는 **일부러 느린** 해시다. `asyncio.to_thread` 로 감싸 비동기 서버를 블로킹하지 않게 한다.

### deps.py — 토큰 → 로그인 유저 (`CurrentUser`)
```python
CurrentUser = Annotated[User, Depends(get_current_active_user)]
```
라우터에서 이렇게만 쓰면 끝:
```python
@router.get("/me")
async def me(current_user: CurrentUser):   # ← 헤더의 Bearer 토큰을 풀어 User 객체로 주입
    ...
```
내부적으로 `Authorization: Bearer <token>` → `decode_token` → `sub`(UUID)로 DB 조회 → 활성(`data_stat_cd="50"`) 유저 반환. 토큰이 없거나/만료/위조면 401.

`extract.py` 의 `extract_user_id(request)` 는 비슷하지만 **실패해도 None을 반환**한다 — 미들웨어(로그·멱등성)에서 "있으면 쓰고 없으면 말고"용.

---

## 7. idempotency/ — POST 중복요청 방지 (이 프로젝트의 백미)

**문제 상황:** 사용자가 "거래 추가"를 눌렀는데 네트워크가 느려 두 번 눌렀다 → 거래가 2개 생기면 안 된다.

**해결:** 프론트가 요청에 `Idempotency-Key` 헤더(랜덤 고유값)를 붙이면, 같은 키의 두 번째 요청은 **새로 처리하지 않고 첫 응답을 그대로 재생**한다.

### 언제 작동하나 (게이트 조건)
`IdempotencyMiddleware` 는 아래 **셋 다** 일 때만 개입한다:
1. **POST** 요청이고
2. `Idempotency-Key` 헤더가 있고
3. 유효한 JWT로 사용자를 알아낼 수 있을 때

### 키의 정체 = (사용자 + 키 + 요청 지문)
DB의 `idempotency_records` 테이블에 `UniqueConstraint(user_id, key)` 가 걸려 있고, 추가로 **요청 body의 SHA256 지문**(`request_fingerprint`)을 저장한다.

### 상태 머신
```
첫 요청:
  INSERT (ON CONFLICT DO NOTHING)  →  성공 = PENDING 박제 → 라우터 실행
       → 응답 status < 500 이면 → COMPLETED 로 응답까지 저장(캐시)
       → 응답 status ≥ 500 이면 → 레코드 삭제(release) → 재시도 허용

같은 키 두 번째 요청:
  INSERT 충돌 → 기존 레코드 확인
       ├ method/path 다름     → ID001 KEY_CONFLICT
       ├ body 지문 다름        → ID002 BODY_MISMATCH   (같은 키 다른 내용 = 의심)
       ├ 아직 PENDING          → ID003 IN_PROGRESS     (처리 중이니 기다려)
       └ COMPLETED            → 저장된 응답 그대로 반환  ✅ 중복 처리 안 함
```

관련 파일: `middleware.py`(관문), `service.py`(상태 판단), `repository.py`(INSERT ON CONFLICT / cleanup), `model.py`(테이블), `response_codec.py`(응답을 저장·복원 — Set-Cookie 같은 멀티헤더까지 보존).

> 오래된 레코드는 스케줄러가 청소한다(PENDING 60초 / COMPLETED 24시간). ➡ 다음 섹션.

---

## 8. middleware/access_log.py — 요청 한 줄 로그

모든 요청 끝에 이런 줄을 남긴다:
```
POST /transaction/create 200 user=123e4567-... ip=10.0.0.1 45ms
```
- 소요시간(ms), 사용자, IP, 상태코드를 한 줄로.
- `/health` 류는 `DEBUG` 레벨로 강등 → 운영 로그에서 노이즈 제거.

---

## 9. scheduler.py + jobs.py — 정기적으로 도는 작업 5개

APScheduler(`AsyncIOScheduler`, **KST 시간대**)가 켜져서, 정해진 시각에 함수를 돌린다. 등록은 `register_jobs()`, 함수는 `jobs.py` 에 있다.

| 잡 | 시각(KST) | 하는 일 |
|---|---|---|
| `refresh_usd_krw` | 평일 09:00 | USD/KRW 환율 갱신 (미장 시세 갱신 전에 먼저) |
| `refresh_kr_prices` | 평일 16:10 | 국내 시세 갱신 (KOSPI·KOSDAQ, 국장 마감 직후) |
| `refresh_us_prices` | 화~토 09:10 | 미국 시세 갱신 (NASDAQ·NYSE, 미장 마감 후) |
| `cleanup_idempotency` | 매시간 | 멱등성 레코드 TTL 정리 |
| `create_monthly_snapshots` | 매월 1일 00:30 | 지난달 자산 스냅샷 박제 (모든 세대) |

각 잡은 `run_locked_job()` 으로 감싸진다:
```python
async with session.begin():
    if not await try_advisory_lock(session, job_name):   # PostgreSQL advisory lock
        return                                            # 다른 워커가 이미 돌고 있으면 skip
    await fn(session)
```
> **왜 lock?** 서버를 여러 개(멀티 인스턴스) 띄우면 같은 잡이 동시에 5번 돌 수 있다. advisory lock으로 **딱 하나만** 실행되게 막는다. 실무 분산 환경의 흔한 패턴.

이 잡들이 부르는 `exchange_rate` / `market_price` / `account_snapshot` 서비스의 내부는 ➡ 05·07 문서.

---

## 10. pagination.py — 커서 기반 페이징 `CursorPage`

목록 조회는 페이지 번호(1,2,3…)가 아니라 **커서(cursor)** 방식을 쓴다.

```python
class CursorPage(Generic[T]):
    items: list[T]            # 이번 페이지 항목
    next_cursor: str | None   # 다음 페이지 시작점 (예: "last_mdfcn_dt|<uuid>")
    has_next: bool            # 다음 페이지 있나?
    total_count: int | None   # 전체 개수 (검색/관리 화면만 채움)
```
- **무한 스크롤** 에 적합: `has_next` 만 보고 더 불러온다.
- 거래내역처럼 계속 쌓이는 목록에서 페이지 번호 방식보다 안정적(중간에 데이터 추가돼도 안 밀림).

---

## 11. 자잘하지만 자주 보이는 유틸

| 파일 | 역할 |
|---|---|
| `dates.py` | `today_kst()` — 서버가 UTC여도 **한국 시각 기준 오늘**. 거래일 경계가 어긋나지 않게. |
| `types.py` | `Money`/`Rate`(소수 2자리)·`Quantity`(소수 4자리) — 금액·수량을 Decimal로 다루고 JSON엔 float로. |
| `schema.py` | `CamelBaseModel` — snake_case ↔ camelCase 자동 변환 + ORM 객체에서 바로 생성(`from_attributes`). |
| `enums/data_status.py` | `DataStatus.ACTIVE="50"` / `DELETED="99"` — soft delete 값. |

---

## 이 문서에서 꼭 기억할 규칙

1. **`get_db` = 트랜잭션 경계.** 서비스는 `flush()` 만, commit/rollback은 요청 끝에 자동.
2. **모든 모델은 `BaseEntity` 상속** → id(UUID)·생성/수정일시·`data_stat_cd` 공짜. 관계는 `relationship()` 안 쓰고 **논리 FK + 서비스 검증**.
3. **응답 = `ApiResponse` 봉투, 에러 = `raise CustomException(ErrorCode.X)`.** 핸들러가 변환.
4. **`CurrentUser`** 를 인자에 쓰면 로그인 유저 자동 주입.
5. **멱등성**: POST + `Idempotency-Key` + 로그인 → 중복 요청은 첫 응답 재생.
6. **스케줄러 5잡** + advisory lock으로 중복 실행 방지.

---

## 다음 문서
➡ **`02-auth-user-household.md`** — 이제 실제 도메인으로. 위에서 본 JWT·CurrentUser가 회원가입→로그인→토큰갱신 흐름에서 어떻게 쓰이고, "부부가 한 세대로 묶이는" household 개념과 `CurrentHousehold`(X-Household-Id 헤더)를 본다.
