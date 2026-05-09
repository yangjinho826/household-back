# household-back

부부 공유 가계부 백엔드. `ai-router-api` 스택 그대로 (FastAPI / SQLAlchemy 2.x async / asyncpg / JWT).

## 빌드/실행

```bash
# 의존성 설치
uv sync

# 환경변수 세팅 (예시 복사 후 수정)
cp .env.example .env

# 개발 서버
uv run uvicorn app.main:app --reload

# Docker 개발 환경 (Postgres + app)
docker compose -f docker-compose.yml up
```

서버 기동 후: `GET /v1/health` 로 핑 확인.

## 디렉토리 구조

```
app/
├── main.py                 # FastAPI 앱 + 라우터 등록 + 예외 핸들러 + CORS
├── core/                   # 공통 인프라
│   ├── api_response.py     # ApiResponse[T] 응답 래퍼
│   ├── config.py           # pydantic-settings 설정
│   ├── database.py         # async engine/session, get_db 의존성
│   ├── model.py            # Base, BaseEntity (UUID + 감사 + data_stat_cd)
│   ├── logging.py          # 콘솔 + 일별 파일 로테이션
│   ├── auth/               # JWT, 비밀번호 해싱, 인증 의존성 (deps.py 는 user 도메인 추가 시)
│   ├── enums/              # DataStatus 등 공통 enum
│   └── exceptions/         # CustomException + ErrorCode + 4종 핸들러
└── domain/
    └── health/             # /health 엔드포인트
```

## 도메인 추가 예정 (다음 단계)

| 도메인 | 테이블 |
|---|---|
| auth | refresh_tokens |
| user | users |
| household | households + household_members |
| account | accounts + account_snapshots |
| category | categories |
| transaction | transactions |
| fixed_expense | fixed_expenses |
| portfolio | portfolio_items + portfolio_value_history |

각 도메인 = 한 폴더 = 6파일 (`model.py`, `schema.py`, `repository.py`, `service.py`, `router.py`, `enum.py`).

## 핵심 규약

| 항목 | 값 |
|---|---|
| Python | 3.14 |
| ASGI | uvicorn |
| ORM | SQLAlchemy 2.x async + asyncpg |
| 인증 | JWT (access Bearer + refresh HttpOnly cookie) |
| ID | UUID (`uuid.uuid4()`) |
| 감사 필드 | `frst_reg_dt`, `last_mdfcn_dt` (onupdate), `data_stat_cd` |
| 응답 래퍼 | `ApiResponse[T]` — `.ok(data)` / `.fail(status, code, message)` |
| 예외 | `CustomException(ErrorCode)` — 핸들러가 `ApiResponse.fail` 변환 |
| Soft Delete | `data_stat_cd = "99"` (ACTIVE="50") |
| API prefix | `/v1` (FastAPI `root_path`) |
| 트랜잭션 | `get_db` 가 자동 commit/rollback. 서비스는 `db.flush()` 만 |
| 서비스 | 모듈 함수 (`service.create_user(db, req)`) — 클래스 X |
| 레포지토리 | 클래스 (`__init__(self, db)`) |
