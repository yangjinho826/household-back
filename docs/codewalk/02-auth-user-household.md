# 02. auth · user · household — 로그인하고, "한 세대"로 묶이기

> 여기서부터 실제 도메인이다. 01에서 본 도구(JWT·`CurrentUser`)가 **회원가입 → 로그인 → 토큰갱신** 흐름에서 어떻게 쓰이는지 보고, 이 가계부의 핵심 개념인 **"부부가 한 세대(household)로 묶인다"** 와 그 관문인 `CurrentHousehold`(X-Household-Id 헤더)를 잡는다.

> 세 도메인이 한 묶음이다. **user**(개인 계정) → **auth**(그 계정으로 로그인) → **household**(여러 user가 모이는 공유 단위). 뒤 문서(account·transaction…)의 데이터는 전부 household에 매달리므로, 여기를 잡으면 나머지 소유 관계가 한 번에 풀린다.

> **이 문서 읽는 법:** §4(공통 메커니즘)에 권한 검증·JWT·cascade 같은 "여러 API가 공유하는 로직"을 한 번 깊게 뒀다. §5(엔드포인트별 트레이스)는 API 16개를 **요청부터 응답까지** 따라가며 공통은 `→ §4-x` 로 참조한다.

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
| **다대다(N:M) + 중간 테이블** | user와 household는 "여러 명이 여러 가계부에" 속할 수 있다 → `household_members` 중간 테이블로 연결. |

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

> **왜 DB에 토큰을 저장?** JWT는 원래 "서버가 기억 안 해도 검증되는" 토큰이다. 그런데 refresh는 **로그아웃·강제만료**를 하려면 서버가 "이 토큰 죽었음"을 알아야 한다. 그래서 refresh만 DB로 추적한다. (access는 저장 안 함 → 30분 뒤 알아서 만료)

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
| `currency` | CHAR(3), 예: `KRW` (생성 시 정확히 3자 검증) |
| `started_at` | 가계부 집계 시작일 (미지정 시 오늘) |

`household_members.role` 은 enum `HouseholdRole` = `OWNER` / `MEMBER` (`app/domain/household/enum.py`).

> **이게 이 앱의 데이터 소유 구조의 뿌리다.** account·transaction·portfolio… 모든 데이터는 `household_id` 를 달고 있고, "이 가계부에 접근할 자격" 은 **`household_members` 에 내 row가 있는가** 로 판가름난다. → §4-1 `CurrentHousehold`.

---

## 4. 공통 메커니즘

세 도메인의 API가 공유하는 로직. §5 트레이스가 여길 참조한다.

> 📦 **repository 공통 패턴 (전 도메인 동일):** 모든 조회 쿼리는 `data_stat_cd == ACTIVE` 를 **항상** 끼운다 → soft-delete된 행은 어떤 조회에도 안 잡힌다(별도 "삭제 제외" 코드 불필요). 예외는 `find_active_by_user_id`(household/repository.py:25) — "내가 멤버인 가계부"를 찾느라 `households ⋈ household_members` JOIN.

### 4-1. 권한 검증 3종 세트 — 언제 뭘 쓰나

"검증"이 세 결로 갈린다. 헷갈리기 쉬워 한 번에 정리:

| 검증 | 쓰는 곳 | 가계부 식별 | 통과 조건 | 실패 |
|---|---|---|---|---|
| **`CurrentHousehold`** | account·transaction 등 **하위 데이터** API | `X-Household-Id` **헤더** | 멤버 row 존재 | HH001 (403) |
| **`_require_membership`** | 멤버 목록 조회 (멤버면 OK) | 경로 `{household_id}` | 멤버 row 존재 | HH001 (403) |
| **`_require_owner`** | 수정·삭제·멤버 추가/제거 | 경로 `{household_id}` | **owner 본인** | HH003 (403) |

```python
# app/domain/household/deps.py:18  get_current_household (= CurrentHousehold)
member = await HouseholdMemberRepository(db).find_by_household_and_user(x_household_id, current_user.id)
if not member:     raise CustomException(ErrorCode.HOUSEHOLD_NOT_MEMBER)   # HH001
household = await HouseholdRepository(db).find_by_id(x_household_id)
if not household:  raise CustomException(ErrorCode.HOUSEHOLD_NOT_FOUND)    # HH002
return household
```
```python
# app/domain/household/service.py:320  _require_owner
if not household:                  raise CustomException(ErrorCode.HOUSEHOLD_NOT_FOUND)  # HH002
if household.owner_id != user_id:  raise CustomException(ErrorCode.HOUSEHOLD_NOT_OWNER)  # HH003
```

> 차이의 핵심: **헤더냐 경로냐** + **멤버면 되냐 owner여야 하냐.** 하위 데이터(통장·거래)는 헤더(`CurrentHousehold`), 가계부 자체를 다루는 API는 경로 ID + `_require_*`.

### 4-2. JWT access/refresh lifecycle

```
로그인 ─┬─ access  (30분, body로 전달, DB 저장 X)
        └─ refresh (7일, HttpOnly 쿠키 + refresh_tokens DB 저장)

access 만료 → POST /auth/refresh (쿠키 자동첨부) → 새 access만 발급 (refresh는 그대로)
로그아웃     → refresh DB 폐기(data_stat_cd=99) + 쿠키 삭제
```
- **검증 2단** (refresh): JWT 서명·만료(`decode_token`) **+** DB 생존 확인(`find_active_by_token`). DB 단계가 있어 로그아웃·강제만료가 가능.
- **기기당 활성 토큰 5개 제한**(`MAX_ACTIVE_TOKENS`, service.py:21): 로그인 시 6번째면 가장 오래된 refresh부터 폐기.
- 토큰 만들기/풀기 도구(`create_*_token`/`decode_token`)·`type`(access/refresh) 구분은 → 01 §6.

### 4-3. 비밀번호 — bcrypt (이벤트 루프 안 막게)

```python
await hash_password(pw)            # 회원가입·비번변경 시 (bcrypt 해시)
await verify_password(pw, hashed)  # 로그인 시 비교
```
> bcrypt는 **일부러 느린** 해시라 비동기 서버를 블로킹할 수 있다. 그래서 `asyncio.to_thread` 로 별도 스레드에서 돌린다(→ 01 §6). 그래서 호출부가 전부 `await`.

### 4-4. list 응답 — `CursorPage` 봉투만 빌린다

`list_households`(service.py:42)·`list_household_members`(:138)의 응답 타입은 `CursorPage` 지만 **실제 페이징은 안 한다**(`next_cursor=None, has_next=False`). 한 사람의 가계부는 보통 1~5개, 한 가계부 멤버는 1~10명이라 커서가 의미 없어서다. **응답 봉투 모양만 다른 목록 API들과 통일**한 것(프론트가 같은 형식으로 처리).

### 4-5. 가계부 삭제 — 통장 삭제보다 넓은 cascade

```python
# app/domain/household/service.py:254
_CHILD_MODELS_WITH_HOUSEHOLD_ID = (
    Account, Category, Transaction,
    PortfolioItem, PortfolioTransaction, PortfolioValueHistory,
    FixedExpense, HouseholdMember,        # household_id 가진 8개 모델
)
# service.py:266 — 각 모델을 통째로 UPDATE: WHERE household_id=? AND ACTIVE → DELETED
# account_snapshots 만 household_id 없어, 그 가계부의 통장 id 서브쿼리로 따로
```
> 03의 **통장** 삭제는 이체 때문에 "순서 중요"였다. **가계부** 삭제는 **순서 무관** — 물리 FK cascade가 아니라 `data_stat_cd` 를 `99`로 바꾸는 UPDATE라, 가계부 통째로 사라지므로 "상대 통장 보존" 고민이 없다.

---

## 5. 엔드포인트별 풀 트레이스

`root_path="/api"` + prefix → 실제 URL은 `POST /api/auth/login` 식.

### user — `/user`

#### POST /user — 회원가입 (인증 불필요)
```
요청  POST /api/user  {email, name, password, language?}
─[1] 검증          router.py:15  create
      UserCreateRequest model_validator(schema.py:38):
        email 1~255+정규식(US003) · password 8~64+영문+숫자(US004) · name 1~100(US005)
─[2] 서비스        service.py:13  create_user
      email.strip().lower() 정규화 → repo.find_by_email 중복검사 → 있으면 USER_DUPLICATE_EMAIL(US002)
      password_hash = await hash_password(pw)                        → §4-3
      User(... data_stat_cd=ACTIVE) → repo.save (add+flush)
─[3] 응답 조립     router.py:22  UserResponse.model_validate(user)   ← password_hash 제외
─[4] 트랜잭션 종료  get_db — commit (INSERT 확정)
응답  ApiResponse.ok(UserResponse)
```
> 회원가입은 **가계부를 자동 생성하지 않는다.** 가입 후 `POST /household/create` 를 따로 호출해야 데이터를 담을 그릇이 생긴다.

#### GET /user/me — 내 정보 (CurrentUser)
```
요청  GET /api/user/me   + Bearer
─[1] 의존성        router.py:25  current_user: CurrentUser → 토큰 디코드 → sub(UUID)로 활성 유저 조회 → 없으면 401
─[2] 서비스        (없음) — 의존성이 이미 User를 들고 옴
─[3] 응답 조립     UserResponse.model_validate(current_user)
응답  ApiResponse.ok(UserResponse)   ← 새로고침/SSR hydrate 용
```

#### GET /user/search?email= — 이메일 검색 (멤버 초대용)
```
요청  GET /api/user/search?email=spouse@x.com   + Bearer
─[1] 의존성·검증   router.py:31  CurrentUser(인증 가드) · email Query(min 3, max 255)
─[2] 서비스        service.py:41  search_by_email
      email.strip().lower() → repo.find_by_email (정확매칭, 부분검색 X) → 미가입이면 NOT_FOUND
─[3] 응답 조립     UserResponse
응답  ApiResponse.ok(UserResponse)
```
> **멤버 초대 흐름 1단계.** 여기서 얻은 `user_id` 를 `POST /household/{id}/members` 에 넣는다.

#### GET /user/{user_id} — 상세 / PUT /user/{user_id} — 수정
```
GET   router.py:42 → service.py:33 detail_user → find_by_id → 없으면 NOT_FOUND (CurrentUser 인증 가드)
PUT   router.py:53 → service.py:51 update_user
      ─ 가드: user_id != current_user.id → FORBIDDEN (남의 프로필 수정 차단)
      ─ 검증: UserUpdateRequest(schema.py:51) — password/name 주면 규칙 검증
      ─ 부분수정: user.update(...) 가 None 필드는 건너뜀, password 주면 다시 해싱(§4-3)
      ─ flush → commit
응답  ApiResponse.ok(UserResponse)
```

### auth — `/auth`

#### POST /auth/login — 로그인 (인증 불필요)
```
요청  POST /api/auth/login  {email, password}
─[1] 검증          router.py:51  LoginRequest (email/password)
─[2] 서비스        service.py:24  login
      repo.find_by_email → 없으면 LOGIN_FAILED · 비활성 계정이면 FORBIDDEN
      verify_password 불일치 → LOGIN_FAILED   ← ①없음/③틀림 같은 에러(계정 존재 노출 방지) §4-3
      활성 refresh 5개↑면 오래된 것부터 폐기                              → §4-2
      access(30분)+refresh(7일) 발급 → refresh를 refresh_tokens DB 저장
─[3] 쿠키·응답     router.py:22  _set_refresh_cookie (HttpOnly, secure, samesite=lax)
      body엔 access만, refresh는 쿠키로만
─[4] 트랜잭션 종료  get_db — commit (refresh INSERT + 초과폐기 UPDATE 확정)
응답  ApiResponse.ok(TokenResponse{accessToken, user})  + Set-Cookie: refresh_token
```

#### POST /auth/refresh — access 재발급 (쿠키 인증)
```
요청  POST /api/auth/refresh   (Cookie: refresh_token 자동첨부)
─[1] 입력          router.py:61  refresh_token: Cookie(...)
      쿠키 없으면 → _refresh_failure_response(INVALID_REFRESH_TOKEN) + 죽은 쿠키 삭제
─[2] 서비스        service.py:72  refresh
      decode_token (만료→EXPIRED_TOKEN / 위조→INVALID)        ← ① JWT 서명·만료 §4-2
      type != REFRESH → INVALID (access 토큰으로 refresh 시도 차단)
      find_active_by_token → DB에 살아있나                    ← ② DB 생존 §4-2
      새 access만 발급 (refresh는 그대로)
─[3] 응답 조립     RefreshResponse{accessToken}
      실패 시 router.py:39 — 죽은 refresh 쿠키 삭제 → 프론트 폴링 루프 차단
응답  ApiResponse.ok(RefreshResponse)
```

#### POST /auth/logout — 로그아웃 (멱등)
```
요청  POST /api/auth/logout   (Cookie: refresh_token)
─[1] 입력          router.py:81  refresh_token: Cookie(...)
─[2] 서비스        service.py:112  logout — 활성 토큰 있으면 data_stat_cd=99 + revoked_at 기록
                   (없어도 조용히 통과 — 이미 폐기/위조여도 에러 X = 멱등)
─[3] 쿠키          router.py:35  _delete_refresh_cookie
응답  ApiResponse.ok()
```

### household — `/household`

#### GET /household/list — 내가 멤버인 가계부 목록
```
요청  GET /api/household/list   + Bearer
─[1] 의존성        router.py:23  CurrentUser
─[2] 서비스        service.py:42  list_households
      repo.find_active_by_user_id → households ⋈ household_members JOIN (내가 멤버인 것)  → §4 박스
      각 가계부 role 판정 (owner_id==나 면 OWNER, 아니면 MEMBER)
─[3] 응답 조립     CursorPage 봉투만 (실제 페이징 X)                              → §4-4
응답  ApiResponse.ok(HouseholdListResponse)
```

#### POST /household/create — 가계부 생성
```
요청  POST /api/household/create  {name, currency?, description?, startedAt?}  + Bearer
─[1] 의존성·검증   router.py:33  CurrentUser · HouseholdCreateRequest(schema.py:18): name 1~100, currency 정확히 3자
─[2] 서비스        service.py:64  create_household
      Household(owner_id=나, currency=upper, started_at=req ?? today) → save
      ★ HouseholdMember(role=OWNER) 자동 INSERT — owner를 멤버로 등록
─[3] 응답 조립     _build_response(household, OWNER)
─[4] 트랜잭션 종료  get_db — commit (household + member 두 INSERT 확정)
응답  ApiResponse.ok(HouseholdResponse{role: OWNER})
```
> **왜 owner 자동 등록?** 권한 판정 기준이 오직 `household_members`(§4-1). owner를 멤버로 안 넣으면 만든 사람조차 자기 가계부에 못 들어간다.

#### GET /household/detail/{id} — 단건 (멤버만)
```
router.py:44 → service.py:216  get_household_detail
  find_by_id + 활성 가드 → HOUSEHOLD_NOT_FOUND
  멤버십 조회 → 멤버 아니면 HOUSEHOLD_NOT_FOUND (멤버 아닌 사람에겐 "없는 것처럼")
  role 판정 → _build_response
응답  ApiResponse.ok(HouseholdResponse)
```

#### PUT /household/update/{id} · DELETE /household/delete/{id} — owner 전용
```
PUT     router.py:55 → service.py:94  update_household
          _require_owner (§4-1) → None 아닌 필드만 수정(name/currency 검증) → flush → commit
DELETE  router.py:67 → service.py:121  delete_household
          _require_owner → _cascade_soft_delete_children (8개 모델 + 스냅샷, 순서무관) → 본체 DELETED  → §4-5
응답  PUT: HouseholdResponse / DELETE: ok()(data 없음)
```

#### GET /household/{id}/members — 멤버 목록
```
router.py:78 → service.py:138  list_household_members
  _require_membership (멤버면 OK) → 멤버 조회 → user_id들로 UserRepository.find_by_ids 배치 → 이름/이메일 채움
  CursorPage 봉투만 (§4-4)
응답  ApiResponse.ok(HouseholdMemberListResponse)
```

#### POST /household/{id}/members — 멤버 추가 (owner만)
```
요청  POST /api/household/{id}/members  {userId, role?}  + Bearer
─[1] 검증          router.py:89  HouseholdMemberCreateRequest(schema.py:68): role==OWNER 면 BAD_REQUEST (API로 OWNER 추가 금지)
─[2] 서비스        service.py:161  add_household_member
      _require_owner (§4-1) → 대상 user 조회(없으면 NOT_FOUND) → 이미 멤버면 HOUSEHOLD_MEMBER_ALREADY
      HouseholdMember(role=MEMBER) save
─[3] 응답 조립     _build_member_response (대상 user 이름/이메일 포함)
응답  ApiResponse.ok(HouseholdMemberResponse)
```

#### DELETE /household/{id}/members/{member_id} — 멤버 제거 (owner만)
```
router.py:101 → service.py:195  remove_household_member
  _require_owner → member 조회(household 불일치/없음 → HOUSEHOLD_MEMBER_NOT_FOUND)
  ★ member.user_id == owner_id 면 HOUSEHOLD_OWNER_CANNOT_LEAVE (owner는 자기 가계부 못 떠남)
  member.data_stat_cd = DELETED
응답  ApiResponse.ok()
```

---

## 6. 데이터 흐름 (큰 그림)

```
POST /api/user            {email,name,password}
   └ 검증 → 중복검사 → bcrypt 해싱 → users INSERT

POST /api/auth/login      {email,password}
   └ 비번검증 → access(30m)+refresh(7d) → refresh DB저장
   ← body:{accessToken,user}  + Set-Cookie: refresh_token(HttpOnly)

POST /api/household/create   Bearer   {name,currency}
   └ households INSERT + household_members INSERT(role=OWNER)
   ← {id, role:"OWNER"}

GET  /api/account/list    Bearer  +  X-Household-Id
   └ CurrentUser(토큰) → CurrentHousehold(멤버십, 아니면 HH001) → 통장 목록

access 만료 → POST /api/auth/refresh (쿠키 자동) → 새 access (실패 시 죽은 쿠키 삭제)
```

---

## 7. 이 문서에서 꼭 기억할 규칙

1. **회원가입 ≠ 가계부 생성.** 가입 후 `/household/create` 를 따로 호출해야 데이터 그릇이 생긴다.
2. **로그인 = access(body) + refresh(HttpOnly 쿠키).** refresh만 DB 저장해 로그아웃·강제만료 가능. 기기당 5개 제한(§4-2).
3. **`/auth/refresh` 는 access만 재발급.** 검증은 JWT 서명 + DB 생존 2단.
4. **데이터 요청엔 헤더 2개**: `Authorization`(나 누구) + `X-Household-Id`(어느 가계부). `CurrentHousehold` 가 멤버십 검증 — 아니면 HH001(§4-1).
5. **권한의 단일 기준 = `household_members` row.** 그래서 가계부 생성 시 owner를 멤버로 자동 등록, owner는 자기 가계부를 못 떠난다.
6. **API로 OWNER 멤버 추가 불가** — OWNER는 생성 시 1명 고정, 멤버 추가는 MEMBER만.

---

## 다음 문서
➡ **`03-account.md`** — `X-Household-Id` 로 진입한 첫 하위 데이터, **통장(account)**. 통장 타입 8종, 잔액이 **저장이 아니라 계산되는** 구조, `is_archived`(보관)와 soft-delete(삭제)의 차이를 본다.
