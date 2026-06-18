# 02. auth · user · household — 로그인하고, "한 세대"로 묶이기

> 여기서부터 실제 도메인이다. 01에서 본 도구(JWT·`CurrentUser`)가 **회원가입 → 로그인 → 토큰갱신** 흐름에서 어떻게 쓰이는지 보고, 이 가계부의 핵심 개념인 **"부부가 한 세대(household)로 묶인다"** 와 그 관문인 `CurrentHousehold`(X-Household-Id 헤더)를 잡는다.

> 이 세 도메인은 한 묶음이다. **user**(개인 계정) → **auth**(그 계정으로 로그인) → **household**(여러 user가 모이는 공유 단위). 뒤 문서(account·transaction…)의 데이터는 전부 household에 매달리므로, 여기를 잡으면 나머지 소유 관계가 한 번에 풀린다.

---

## 1. 이 세 도메인 한마디

| 도메인 | 담당 | 테이블 |
|---|---|---|
| **user** | 개인 계정 (이메일·이름·비밀번호) | `users` |
| **auth** | 로그인 / 토큰 발급 / refresh 토큰 관리 | `refresh_tokens` |
| **household** | 가계부 = 세대(부부 공유 단위) + 멤버 | `households`, `household_members` |

> 핵심 그림: **user는 "사람", household는 "가계부 한 권", household_member는 "누가 어느 가계부에 속하는지"** 를 잇는 연결고리.

---

## 2. 들어가기 전 (개념 콕)

| 개념 | 한마디 |
|---|---|
| **Access / Refresh 토큰** | Access = 짧게 사는 출입증(30분), Refresh = 길게 사는 재발급권(7일). Access 만료되면 Refresh로 새로 받는다. |
| **HttpOnly 쿠키** | JS가 못 읽는 쿠키. Refresh 토큰을 여기 담아 탈취 위험을 줄인다. |
| **`Header(alias=...)`** | 특정 HTTP 헤더 값을 함수 인자로 주입받는 FastAPI 기능. `CurrentHousehold`가 `X-Household-Id`를 이렇게 받는다. |
| **다대다(N:M) + 중간 테이블** | user와 household는 "여러 명이 여러 가계부에" 속할 수 있다 → `household_members` 라는 중간 테이블로 연결. |

---

## 3. 데이터 모델

### user — `users`
| 컬럼 | 타입 | 의미 |
|---|---|---|
| `email` | String(255) | 로그인 ID. 항상 **소문자로 정규화**해 저장 |
| `name` | String(100) | 표시 이름 |
| `password_hash` | String(255) | **bcrypt 해시** (평문 저장 X) |
| `language` | String(10) | `"ko"` / `"en"` (기본 `ko`) |

`+ BaseEntity` (id·생성/수정일시·`data_stat_cd`). 삭제는 `soft_delete()` → `data_stat_cd="99"`.

### auth — `refresh_tokens`
| 컬럼 | 타입 | 의미 |
|---|---|---|
| `user_id` | UUID | 누구 토큰인지 (논리 FK) |
| `token` | String(512) | 발급된 refresh JWT 문자열 |
| `expires_at` | DateTime | 만료 시각 |
| `revoked_at` | DateTime\|null | 폐기된 시각 (로그아웃·초과폐기 시 기록) |

> **왜 DB에 토큰을 저장하지?** JWT는 원래 "서버가 기억 안 해도 검증되는" 토큰이다. 그런데 refresh는 **로그아웃·강제만료**를 하려면 서버가 "이 토큰 죽었음"을 알아야 한다. 그래서 refresh만 DB로 추적한다. (access는 저장 안 함 → 30분 뒤 알아서 만료)

### household — `households` + `household_members`

```
households (가계부 한 권)            household_members (누가 어느 가계부에)
┌──────────────────┐               ┌────────────────────────────┐
│ name   가계부명   │   1 : N       │ household_id   어느 가계부   │
│ owner_id 소유자  │◀──────────────│ user_id        어느 사용자   │
│ currency 통화    │               │ role   OWNER / MEMBER       │
│ started_at 시작일│               │ joined_at  가입시각          │
└──────────────────┘               └────────────────────────────┘
```

| household 컬럼 | 의미 |
|---|---|
| `owner_id` | 만든 사람(소유자) UUID — 논리 FK |
| `currency` | CHAR(3), 예: `KRW` |
| `started_at` | 가계부 집계 시작일 (미지정 시 오늘) |

`household_members.role` 은 enum `HouseholdRole` = `OWNER` / `MEMBER` (`app/domain/household/enum.py`).

> **이게 이 앱의 데이터 소유 구조의 뿌리다.** account·transaction·portfolio… 모든 데이터는 `household_id` 를 달고 있고, "이 가계부에 접근할 자격" 은 **`household_members` 에 내 row가 있는가** 로 판가름난다. → 섹션 4-4 `CurrentHousehold`.

---

## 4. 핵심 로직 코드리딩

### 4-1. 회원가입 — user 도메인

```python
# app/domain/user/service.py:13  create_user
email = req.email.strip().lower()                 # (1) 이메일 정규화 (대소문자 혼동 방지)
if await repo.find_by_email(email):               # (2) 중복 검사
    raise CustomException(ErrorCode.USER_DUPLICATE_EMAIL)   # US002
user = User(
    email=email,
    name=req.name.strip(),
    password_hash=await hash_password(req.password),   # (3) bcrypt 해싱 (평문 저장 X)
    language=req.language,
    data_stat_cd=DataStatus.ACTIVE,
)
await repo.save(user)                              # (4) 저장 (commit은 요청 끝에 get_db가)
```

> ✅ 기억: 회원가입은 **가계부를 자동으로 만들지 않는다.** 가입 후 사용자가 직접 `POST /household/create` 로 가계부를 만든다. (입문자가 "가입했는데 왜 가계부가 없지?" 하는 지점 — 의도된 분리)

### 4-2. 로그인 — auth 도메인

```python
# app/domain/auth/service.py:24  login
user = await user_repo.find_by_email(email)
if not user:                          raise CustomException(ErrorCode.LOGIN_FAILED)   # (1) 사용자 없음
if user.data_stat_cd != DataStatus.ACTIVE:  raise CustomException(ErrorCode.FORBIDDEN)  # (2) 비활성 계정
if not await verify_password(req.password, user.password_hash):                       # (3) 비번 검증
    raise CustomException(ErrorCode.LOGIN_FAILED)

# (4) 활성 refresh 토큰이 5개(MAX_ACTIVE_TOKENS) 이상이면 오래된 것부터 폐기
existing = await token_repo.find_active_by_user_id(user.id)
if len(existing) >= MAX_ACTIVE_TOKENS:
    ...  # 가장 오래된 토큰 data_stat_cd=DELETED + revoked_at 기록

access_token  = create_access_token(token_data)    # (5) 30분짜리
refresh_token = create_refresh_token(token_data)   # (6) 7일짜리
await token_repo.save(RefreshToken(... token=refresh_token ...))  # (7) refresh만 DB 저장
return TokenResponse(access_token=..., user=...), refresh_token
```

세 가지 포인트:
- **(1)·(3) 둘 다 같은 에러(`LOGIN_FAILED`)** — "이메일이 없는지 / 비번이 틀린지" 를 구분해 알려주지 않는다. 계정 존재 여부 노출 방지.
- **(4) 토큰 5개 제한** — 기기 무한 누적을 막는다(폰·태블릿·PC… 6번째 로그인 시 가장 오래된 세션 강제 로그아웃).
- **(7) refresh만 DB에 박는다** — access는 저장 안 함(섹션 3 참고).

라우터는 받은 refresh를 **HttpOnly 쿠키**로 내려준다:
```python
# app/domain/auth/router.py:22  _set_refresh_cookie
response.set_cookie(
    key="refresh_token", value=refresh_token,
    httponly=True,                       # JS 접근 차단 (XSS 방어)
    secure=settings.COOKIE_SECURE,       # 운영(HTTPS)에선 True
    samesite="lax",
    max_age=settings.JWT_REFRESH_EXPIRATION,
)
```
→ 응답 body엔 **access 토큰만**, refresh는 **쿠키로만** 나간다. 프론트는 refresh를 직접 만질 일이 없다.

### 4-3. 토큰 갱신 — `POST /auth/refresh`

access가 만료되면, 프론트는 그냥 `/auth/refresh` 를 부른다(쿠키는 브라우저가 자동 첨부).

```python
# app/domain/auth/service.py:72  refresh
payload = decode_token(refresh_token)            # (1) 서명·만료 검증 (틀리면 예외)
if payload.get("type") != TokenType.REFRESH:     # (2) access 토큰으로 refresh 시도 차단
    raise CustomException(ErrorCode.INVALID_REFRESH_TOKEN)
token_entity = await token_repo.find_active_by_token(refresh_token)   # (3) DB에 살아있는 토큰인가?
if not token_entity:                             # 폐기됐거나 위조 → 거부
    raise CustomException(ErrorCode.INVALID_REFRESH_TOKEN)
access_token = create_access_token(token_data)   # (4) 새 access만 발급 (refresh는 그대로)
return RefreshResponse(access_token=access_token, ...)
```

> ✅ 기억: refresh는 **access만 새로 준다.** refresh 토큰 자체는 7일 만료까지 재사용. 그리고 검증이 **2단**이다 — JWT 서명(1·2) **+** DB 생존 확인(3). DB 단계가 있어서 로그아웃·강제만료가 가능하다.

라우터의 실패 처리가 한 가지 영리하다:
```python
# app/domain/auth/router.py:39  _refresh_failure_response
resp.delete_cookie(key="refresh_token", ...)   # 실패하면 죽은 쿠키를 지워버린다
```
→ 죽은 refresh 쿠키를 들고 무한히 `/refresh` 를 때리는 **프론트 폴링 루프를 끊는다**.

### 4-4. `CurrentHousehold` — 이 앱에서 두 번째로 중요한 의존성

01에서 `CurrentUser`(로그인 유저 주입)를 봤다. 도메인 데이터(통장·거래…)는 한 발 더 나간다 — **"이 유저가 이 가계부의 멤버인가?"** 까지 확인해야 한다. 그게 `CurrentHousehold`.

```python
# app/domain/household/deps.py:18  (전문)
async def get_current_household(
    current_user: Annotated[User, Depends(get_current_active_user)],   # ① 먼저 로그인 검증
    db: Annotated[AsyncSession, Depends(get_db)],
    x_household_id: Annotated[UUID, Header(alias="X-Household-Id")],    # ② 헤더에서 가계부 ID
) -> Household:
    member = await HouseholdMemberRepository(db).find_by_household_and_user(
        x_household_id, current_user.id,                               # ③ 멤버십 조회
    )
    if not member:
        raise CustomException(ErrorCode.HOUSEHOLD_NOT_MEMBER)          # ④ 멤버 아니면 HH001 (403)
    household = await HouseholdRepository(db).find_by_id(x_household_id)
    if not household:
        raise CustomException(ErrorCode.HOUSEHOLD_NOT_FOUND)           # ⑤ 가계부 자체 없으면 HH002
    return household

CurrentHousehold = Annotated[Household, Depends(get_current_household)]
```

라우터에서 쓰는 모습 (account·transaction… 거의 전부 이 패턴):
```python
@router.get("/list")
async def list_accounts(
    household: CurrentHousehold,           # ← 이 한 줄이 로그인+멤버십을 다 검증
    db: AsyncSession = Depends(get_db),
):
    # 여기 도달했다 = "로그인했고, 이 가계부의 멤버다" 가 이미 보장됨
    ...
```

> ✅ 기억: **도메인 데이터 요청엔 헤더 2개가 필요하다.** `Authorization: Bearer <access>` (나 누구) + `X-Household-Id: <uuid>` (어느 가계부). 둘 중 하나라도 빠지거나 멤버가 아니면 401/403. 라우터 안에서 권한 체크 코드를 안 써도, `CurrentHousehold` 한 줄이 다 막아준다.

### 4-5. 가계부 생성 시 owner를 멤버로 자동 등록

```python
# app/domain/household/service.py:64  create_household
household = Household(owner_id=current_user.id, ...)
await household_repo.save(household)
owner_member = HouseholdMember(          # ★ 만든 사람을 곧바로 OWNER 멤버로 등록
    household_id=household.id, user_id=current_user.id,
    role=HouseholdRole.OWNER, ...
)
await member_repo.save(owner_member)
```

> **왜 자동 등록?** 권한 판정 기준이 오직 `household_members` 이기 때문(4-4). owner를 멤버로 안 넣으면, 정작 만든 사람조차 자기 가계부에 `CurrentHousehold` 로 못 들어간다. 멤버 추가(`POST /household/{id}/members`)는 **owner만** 가능하고, API로는 `MEMBER` 역할만 추가된다(OWNER는 생성 시 1명 고정).

---

## 5. API 엔드포인트

### user — `/user`
| Method | Path | 인증 | 설명 |
|---|---|---|---|
| POST | `/user` | — | **회원가입** |
| GET | `/user/me` | CurrentUser | 내 정보 |
| GET | `/user/search?email=` | CurrentUser | 이메일 정확매칭 검색 (멤버 초대용) |
| GET | `/user/{user_id}` | CurrentUser | 상세 |
| PUT | `/user/{user_id}` | CurrentUser | 수정 (본인만) |

### auth — `/auth`
| Method | Path | 인증 | 설명 |
|---|---|---|---|
| POST | `/auth/login` | — | 로그인 → access(body) + refresh(쿠키) |
| POST | `/auth/refresh` | 쿠키 | refresh로 새 access |
| POST | `/auth/logout` | 쿠키 | refresh 폐기 + 쿠키 삭제 |

### household — `/household`
| Method | Path | 인증 | 설명 |
|---|---|---|---|
| GET | `/household/list` | CurrentUser | 내가 멤버인 가계부 목록 |
| POST | `/household/create` | CurrentUser | 가계부 생성 (생성자=owner) |
| GET | `/household/detail/{id}` | CurrentUser | 단건 (멤버만) |
| PUT | `/household/update/{id}` | CurrentUser | 수정 (owner만) |
| DELETE | `/household/delete/{id}` | CurrentUser | soft delete (owner만) |
| GET | `/household/{id}/members` | CurrentUser | 멤버 목록 |
| POST | `/household/{id}/members` | CurrentUser | 멤버 추가 (owner만, MEMBER 역할) |
| DELETE | `/household/{id}/members/{member_id}` | CurrentUser | 멤버 제거 (owner만) |

> household 라우터는 **`CurrentUser` 까지만** 쓴다(`CurrentHousehold` 아님). 가계부 자체를 다루는 API라, "어느 가계부냐" 를 헤더가 아니라 **경로(`{household_id}`)** 로 받고 권한은 서비스가 직접 확인(`_require_owner` 등). `X-Household-Id` 헤더는 **가계부에 매달린 하위 데이터**(account·transaction…)에서 쓴다.

> 실제 URL은 `root_path="/api"` + prefix. 예: `POST /api/auth/login` (→ 01·00 문서 참고).

---

## 6. 데이터 흐름

```
[회원가입 → 로그인 → 가계부 진입]

POST /api/user            {email,name,password}
   └ 중복검사 → bcrypt 해싱 → users INSERT

POST /api/auth/login      {email,password}
   └ 비번검증 → access(30m)+refresh(7d) 발급 → refresh DB저장
   ← body: { accessToken, user }   + Set-Cookie: refresh_token(HttpOnly)

POST /api/household/create   Bearer <access>   {name,currency}
   └ households INSERT + household_members INSERT(role=OWNER)
   ← { id, role: "OWNER" }

GET  /api/account/list    Bearer <access>  +  X-Household-Id: <id>
   └ CurrentUser(토큰검증) → CurrentHousehold(멤버십검증, 아니면 HH001)
   ← 그 가계부의 통장 목록

[access 만료되면]
POST /api/auth/refresh    (쿠키 자동첨부)
   └ JWT검증 + DB생존확인 → 새 access만
   ← { accessToken }       (실패하면 죽은 쿠키 삭제)
```

---

## 7. 이 문서에서 꼭 기억할 규칙

1. **회원가입 ≠ 가계부 생성.** 가입 후 `/household/create` 를 따로 호출해야 데이터를 담을 그릇이 생긴다.
2. **로그인 = access(body) + refresh(HttpOnly 쿠키).** refresh만 DB에 저장해 로그아웃·강제만료를 가능케 한다. 기기당 활성 토큰 5개 제한.
3. **`/auth/refresh` 는 access만 재발급.** 검증은 JWT 서명 + DB 생존 2단.
4. **데이터 요청엔 헤더 2개**: `Authorization`(나 누구) + `X-Household-Id`(어느 가계부). `CurrentHousehold` 가 멤버십까지 검증 — 아니면 **HH001(403)**.
5. **권한의 단일 기준 = `household_members` row.** 그래서 가계부 생성 시 owner를 멤버로 자동 등록한다.

---

## 다음 문서
➡ **`03-account.md`** — `X-Household-Id` 로 진입한 첫 하위 데이터, **통장(account)**. 통장 타입 8종(생활·투자·수동자산…), 잔액이 **저장이 아니라 계산되는** 구조(`start_balance + 거래합`), 그리고 `is_archived`(보관)와 soft-delete(삭제)가 어떻게 다른지 본다.
