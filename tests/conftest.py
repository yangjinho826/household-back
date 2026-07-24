"""테스트 공용 fixture.

주의: 이 파일의 최상단 env 주입은 어떤 app.* import 보다 먼저 실행돼야 한다.
app.core.config.settings 와 app.core.database.engine 이 import 시점에 굳기 때문 —
그 전에 os.environ 을 테스트 PG 로 덮어써야 멱등성 미들웨어(async_session 직접 사용,
DI 아님)까지 같은 테스트 DB 를 본다.
"""

import asyncio
import os
import sys
from pathlib import Path

# Windows 의 기본 ProactorEventLoop 은 asyncpg 커넥션 정리 시 teardown 에서
# 'NoneType has no attribute send' 를 뱉는다. Selector 루프가 asyncpg 와 안정적.
# 모듈 최상단에 둬 asyncio.run(스키마 fixture)·pytest-asyncio 루프 둘 다 커버한다.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_ROOT = Path(__file__).resolve().parent.parent
_ENV_TEST = _ROOT / ".env.test"

# ── app/DB import 보다 먼저 테스트 env 주입 ──
# setdefault 가 아니라 덮어쓰기: 셸/CI 에 prod DATABASE_URL 이 떠 있으면 setdefault 는
# 그걸 남겨 테스트가 운영 DB 를 TRUNCATE 하는 참사가 난다. 무조건 테스트 값이 이긴다.
for _line in _ENV_TEST.read_text(encoding="utf-8").splitlines():
    _line = _line.strip()
    if not _line or _line.startswith("#") or "=" not in _line:
        continue
    _key, _value = _line.split("=", 1)
    os.environ[_key.strip()] = _value.strip()

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import async_session, engine  # noqa: E402
from app.core.model import Base  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    """테스트 DB 스키마를 SQLAlchemy 모델로 생성/정리 (session 1회).

    이 레포의 alembic baseline 은 빈 마이그레이션(운영은 init.sql + `stamp head`)이라
    'upgrade head' 로는 스키마가 안 만들어진다. init.sql 도 코드와 불일치(idempotency
    누락 등)라, 앱이 실제 쿼리에 쓰는 SQLAlchemy 모델이 유일하게 완전한 진실이다.

    모든 fixture·test 가 하나의 session 루프에서 도므로(pyproject loop_scope=session)
    앱 engine 을 그대로 써도 커넥션 풀 루프 바인딩이 안전하다.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_db():
    """매 테스트 종료 후 전 테이블 TRUNCATE.

    tx-rollback 이 아니라 TRUNCATE 인 이유: 멱등성 동시성 테스트는 요청마다 독립 커넥션이
    필요해 단일 커넥션 롤백 fixture 로는 경합이 무효화된다. Base.metadata 에 없는
    alembic_version 은 자동 제외된다.
    """
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def db():
    """테스트용 AsyncSession (factory 로 직접 데이터 심을 때)."""
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    """ASGITransport 기반 async 클라이언트.

    lifespan 을 타지 않아 scheduler 는 안 뜬다(테스트에 불필요). health 등 라우터는
    테스트 engine 을 그대로 사용한다.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
