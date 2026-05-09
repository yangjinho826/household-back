# household-back 구현 필요 API 목록

household-front (`src/_features/<도메인>/api.ts`) 가 호출하는 모든 엔드포인트를 도메인별로 정리. 이 문서는 **목록**만 — 각 도메인의 모델·스키마·라우터 구현은 도메인 단위 별도 작업으로 진행.

---

## 베이스

| 항목 | 값 |
|---|---|
| 경로 prefix | `/api/{도메인}/...` (next.config rewrite 가 `/api/*` → `${BACKEND_URL}/api/*` 그대로 패스) |
| 응답 래퍼 | `{status, code, message, data}` — `app/core/api_response.py` 의 `ApiResponse` 그대로 |
| 페이징 응답 | `data` 안에 `{listSize, currentPage, currentCount, totalElements, totalPages, content[]}` — `ApiListResponse` 헬퍼는 첫 list API 구현 시 추가 |
| 인증 쿠키 | `personal-auth.access` (JWT access) / `personal-auth.refresh` (JWT refresh) / `personal-auth.session.v1` (me JSON) |
| 401 처리 | 프론트가 자동 `POST /api/auth/refresh` 호출 → 200 시 원 요청 재시도 |
| `app/main.py` | `root_path="/v1"` 제거 필요 (첫 도메인 구현 턴에) |

---

## 결정사항 (확정)

| 항목 | 결정 |
|---|---|
| `data_stat_cd` | `'50'` (Active) / `'99'` (Deleted) — 백엔드 `DataStatus` enum 그대로. SQL 주석의 'A/D/I' 는 의미만 50/99 로 해석 |
| 응답 필드 네이밍 | Pydantic `alias_generator=to_camel` + `populate_by_name=True` 자동 변환. DB·내부는 snake_case |
| DB 스키마 관리 | 사용자가 PostgreSQL 에 직접 INSERT. Alembic X. SQLAlchemy 모델은 SQL 에 1:1 매칭하여 작성 |

---

## API 목록 (총 32개)

### 1. auth (5)

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/auth/register` | 회원가입 |
| POST | `/api/auth/login` | 로그인 (3개 쿠키 set) |
| POST | `/api/auth/refresh` | access 토큰 갱신 (401 시 자동 호출) |
| POST | `/api/auth/logout` | 3개 쿠키 삭제 |
| GET | `/api/auth/me` | 현재 사용자 |

### 2. household (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/household/list` | 가계부 목록 |
| POST | `/api/household/create` | 가계부 생성 |
| PUT | `/api/household/update/{id}` | 가계부 수정 |
| DELETE | `/api/household/delete/{id}` | 가계부 삭제 (soft) |

### 3. household member (3)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/household/members` | 응답 형태 특이 — `Record<householdId, Member[]>` 객체 |
| POST | `/api/household/{householdId}/members/create` | 멤버 추가 (owner 만) |
| DELETE | `/api/household/{householdId}/members/{memberId}` | 멤버 추방 |

### 4. account (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/account/list` | 응답 `balance` 는 `start_balance + transactions` 합산으로 service 계산 |
| POST | `/api/account/create` | 통장 생성 |
| PUT | `/api/account/update/{id}` | 통장 수정 |
| DELETE | `/api/account/delete/{id}` | 통장 삭제 (soft) |

### 5. category (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/category/list` | 프론트 `isIncome` ↔ DB `kind` 변환 |
| POST | `/api/category/create` | 카테고리 생성 |
| PUT | `/api/category/update/{id}` | 카테고리 수정 |
| DELETE | `/api/category/delete/{id}` | 카테고리 삭제 (soft) |

### 6. transaction (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/transaction/list` | 거래 목록 |
| POST | `/api/transaction/create` | type: `income` / `expense` / `transfer` (transfer 는 `toAccountId` 필수) |
| PUT | `/api/transaction/update/{id}` | 거래 수정 |
| DELETE | `/api/transaction/delete/{id}` | 거래 삭제 (soft) |

### 7. fixed (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/fixed/list` | 고정지출 참조 목록 |
| POST | `/api/fixed/create` | 고정지출 추가 |
| PUT | `/api/fixed/update/{id}` | 고정지출 수정 |
| DELETE | `/api/fixed/delete/{id}` | 고정지출 삭제 (soft) |

### 8. portfolio (4)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/portfolio/list` | broker 는 `account.name` JOIN 후 응답에 포함 |
| POST | `/api/portfolio/create` | broker 이름 → `account_id` 매핑 |
| PUT | `/api/portfolio/update/{id}` | 종목 수정 |
| DELETE | `/api/portfolio/delete/{id}` | 종목 삭제 (soft) |

---

## 도메인 구현 권장 순서

의존성 고려한 순서. 사용자 지시 우선 — 강요 X.

1. **auth + users** — 모든 도메인의 전제
2. **household + member** — 대부분 도메인이 `household_id` 로 스코프
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
- `household-front/src/_libraries/auth/session.ts` — 인증 쿠키 이름
- `household-front/next.config.mjs` — `/api/*` rewrite

**백엔드 (이미 구현)**
- `app/core/api_response.py` — `ApiResponse` 래퍼
- `app/core/auth/jwt.py` — JWT 토큰 생성·검증
- `app/core/auth/security.py` — bcrypt 해시
- `app/core/model.py` — `BaseEntity` (UUID PK + 감사 필드 + soft delete)
- `app/core/exceptions/error_code.py` — `ErrorCode` enum (CM/AU/US/HH 코드)
