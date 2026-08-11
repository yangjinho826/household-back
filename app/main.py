import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.demo import seed as demo_seed
from app.core.exceptions.handlers import register_exception_handlers
from app.core.idempotency.middleware import IdempotencyMiddleware
from app.core.logging import setup_logging
from app.core.middleware import AccessLogMiddleware
from app.core.scheduler import register_jobs, run_locked_job, scheduler
from app.domain.account.router import router as account_router
from app.domain.account_snapshot.router import router as account_snapshot_router
from app.domain.auth.router import router as auth_router
from app.domain.category.router import router as category_router
from app.domain.enum.router import router as enum_router
from app.domain.fixed.router import router as fixed_router
from app.domain.health.router import router as health_router
from app.domain.home.router import router as home_router
from app.domain.household.router import router as household_router
from app.domain.portfolio.router import router as portfolio_router
from app.domain.settings.router import router as settings_router
from app.domain.stats.router import router as stats_router
from app.domain.transaction.router import router as transaction_router
from app.domain.user.router import router as user_router
from app.domain.wealth.router import router as wealth_router

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """앱 시작/종료 시 실행되는 라이프사이클 관리"""
    await init_db()
    register_jobs()
    scheduler.start()
    if settings.DEMO_SEED_ENABLED:
        # 데이터가 없을 때만 채운다 (새 서버·DB 복구 직후). 시딩은 야후 호출 + 12개월
        # 박제라 수십 초가 걸리므로 백그라운드로 — 기동과 헬스체크를 막지 않는다.
        asyncio.create_task(_bootstrap_demo())
    yield
    scheduler.shutdown(wait=True)
    await close_db()


async def _bootstrap_demo() -> None:
    """데모 부트스트랩 — advisory lock 으로 감싸 인스턴스 2개가 동시에 시딩하지 않게."""
    await run_locked_job("bootstrap_demo", demo_seed.bootstrap_if_empty)


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
    root_path="/api",
)
register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.include_router(health_router)
app.include_router(user_router)
app.include_router(auth_router)
app.include_router(household_router)
app.include_router(account_router)
app.include_router(category_router)
app.include_router(transaction_router)
app.include_router(fixed_router)
app.include_router(account_snapshot_router)
app.include_router(portfolio_router)
app.include_router(stats_router)
app.include_router(home_router)
app.include_router(wealth_router)
app.include_router(settings_router)
app.include_router(enum_router)
