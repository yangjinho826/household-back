# household-back 구현 필요 API 목록

household-front (`src/_features/<도메인>/api.ts`) 가 호출하는 모든 엔드포인트를 도메인별로 정리. 이 문서는 **목록**만 — 각 도메인의 모델·스키마·라우터 구현은 도메인 단위 별도 작업으로 진행.

---

## 베이스

| 항목 | 값 |
|---|---|
| 경로 prefix | `/api/{도메인}/...` (`app/main.py` 의 `root_path="/api"` 적용. 라우터는 prefix 없이 `/auth`, `/user` 등으로 정의) |
| 응답 래퍼 | `{status, code, message, data}` — `app/core/api_response.py` 의 `ApiResponse` 그대로 |
| 페이징 응답 | `data` 안에 `{listSize, currentPage, currentCount, totalElements, totalPages, content[]}` — `ApiListResponse` 헬퍼는 첫 list API 구현 시 추가 |
| 인증 토큰 | access: 응답 바디로 받음 → `Authorization: Bearer <token>` 헤더로 전송 |
| 인증 쿠키 | `refresh_token` (HttpOnly, samesite=strict) — refresh 호출에만 사용 |
| 401 처리 | 프론트가 자동 `POST /api/auth/refresh` 호출 → 응답의 새 `access_token` 으로 원 요청 재시도 |
| JWT 페이로드 | `{sub: user_id, language: ko|en, type: access|refresh, exp}` — 프론트가 토큰 디코드해서 언어셋 사용 |

---

## 결정사항 (확정)

| 항목 | 결정 |
|---|---|
| `data_stat_cd` | `'50'` (Active) / `'99'` (Deleted) — 백엔드 `DataStatus` enum 그대로. SQL 주석의 'A/D/I' 는 의미만 50/99 로 해석 |
| 응답 필드 네이밍 | Pydantic `alias_generator=to_camel` + `populate_by_name=True` 자동 변환. DB·내부는 snake_case |
| DB 스키마 관리 | 사용자가 PostgreSQL 에 직접 INSERT. Alembic X. SQLAlchemy 모델은 SQL 에 1:1 매칭하여 작성 |
| 검증 위치 | schema 의 `model_validator(mode="after")` 에서 `CustomException` raise — 모든 응답이 `ApiResponse + ErrorCode` 형식으로 통일 |

---

## API 목록 (총 33개)

### 1. auth (3)

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/auth/login` | 로그인 → `TokenResponse {access_token, token_type, expires_in, user}` + refresh cookie set |
| POST | `/api/auth/refresh` | refresh cookie → 새 `RefreshResponse {access_token, expires_in}` |
| POST | `/api/auth/logout` | refresh cookie 삭제 |

추가 동작:
- 로그인 시 사용자당 활성 refresh 토큰 5개 제한 (`MAX_ACTIVE_TOKENS`). 초과 시 가장 오래된 거 자동 폐기 (`data_stat_cd=99` + `revoked_at=now`).

### 2. user (3)

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/user` | 회원가입 (`email`, `name`, `password`, `language` ko/en) |
| GET | `/api/user/{id}` | 사용자 상세 |
| PUT | `/api/user/{id}` | 사용자 수정 (본인만 — `current_user.id == user_id` 검증) |

### 3. household (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/household/list` | 현재 user 가 멤버인 가계부 목록 |
| POST | `/api/household/create` | 가계부 생성 — owner_id 자동 할당 + `household_members` 에 owner row 자동 생성 |
| PUT | `/api/household/update/{id}` | 가계부 수정 (owner 만) |
| DELETE | `/api/household/delete/{id}` | 가계부 삭제 (soft, owner 만) |

### 4. household member (3)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/household/members` | 응답 형태 특이 — `Record<householdId, Member[]>` 객체 |
| POST | `/api/household/{householdId}/members/create` | 멤버 추가 (owner 만) |
| DELETE | `/api/household/{householdId}/members/{memberId}` | 멤버 추방 (owner 만) |

### 5. account (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/account/list` | 응답 `balance` 는 `start_balance + transactions` 합산으로 service 계산 |
| POST | `/api/account/create` | 통장 생성 |
| PUT | `/api/account/update/{id}` | 통장 수정 |
| DELETE | `/api/account/delete/{id}` | 통장 삭제 (soft) |

### 6. category (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/category/list` | 프론트 `isIncome` ↔ DB `kind` 변환 |
| POST | `/api/category/create` | 카테고리 생성 |
| PUT | `/api/category/update/{id}` | 카테고리 수정 |
| DELETE | `/api/category/delete/{id}` | 카테고리 삭제 (soft) |

### 7. transaction (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/transaction/list` | 거래 목록 |
| POST | `/api/transaction/create` | type: `income` / `expense` / `transfer` (transfer 는 `toAccountId` 필수) |
| PUT | `/api/transaction/update/{id}` | 거래 수정 |
| DELETE | `/api/transaction/delete/{id}` | 거래 삭제 (soft) |

### 8. fixed (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/fixed/list` | 고정지출 참조 목록 |
| POST | `/api/fixed/create` | 고정지출 추가 |
| PUT | `/api/fixed/update/{id}` | 고정지출 수정 |
| DELETE | `/api/fixed/delete/{id}` | 고정지출 삭제 (soft) |

### 9. portfolio (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/portfolio/list` | broker 는 `account.name` JOIN 후 응답에 포함 |
| POST | `/api/portfolio/create` | broker 이름 → `account_id` 매핑 |
| PUT | `/api/portfolio/update/{id}` | 종목 수정 |
| DELETE | `/api/portfolio/delete/{id}` | 종목 삭제 (soft) |

---

## 도메인 구현 권장 순서

의존성 고려한 순서. 사용자 지시 우선 — 강요 X.

1. ~~**auth + users**~~ — 모든 도메인의 전제 ✅ 완료
2. **household + member** — 대부분 도메인이 `household_id` 로 스코프 (Step 12 의존성)
3. **account / category** — transaction 의존성
4. **transaction** — 핵심 비즈니스
5. **fixed**
6. **portfolio** (+ `portfolio_value_history`, `account_snapshots`)

---

## 참고 파일

**프론트 (읽기 전용 — 도메인별 spec 소스)**
- `household-front/src/_features/{도메인}/api.ts`
- `household-front/src/_features/{도메인}/types.ts`
- `household-front/src/_features/{도메인}/mock.ts`
- `household-front/next.config.mjs` — `/api/*` rewrite

**백엔드 (이미 구현)**
- `app/main.py` — `root_path="/api"` + 라우터 등록
- `app/core/api_response.py` — `ApiResponse` 래퍼
- `app/core/auth/jwt.py` — JWT 토큰 생성·검증 (sub + language 페이로드)
- `app/core/auth/security.py` — bcrypt 해시
- `app/core/auth/deps.py` — `HTTPBearer` 기반 `CurrentUser` 의존성 (활성 상태 체크 포함)
- `app/core/model.py` — `BaseEntity` (UUID PK + 감사 필드 + soft delete)
- `app/core/exceptions/error_code.py` — `ErrorCode` enum (CM/AU/US/HH 코드)
- `app/core/exceptions/handlers.py` — 4종 핸들러 (CustomException / HTTP / Validation / 전역) 모두 ApiResponse 형식 응답
- `app/domain/auth/`, `app/domain/user/`, `app/domain/health/` — 1단계 완료
