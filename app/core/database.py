import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

# 비동기 엔진
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_MIN,
    max_overflow=settings.DB_POOL_MAX - settings.DB_POOL_MIN,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=settings.DEBUG,  # True면 SQL 로그 출력
)

# 세션 팩토리
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def verify_db_connection() -> bool:
    """DB 연결 상태를 확인합니다."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True


async def init_db() -> None:
    """DB 연결 확인 (실패해도 예외를 던지지 않음)"""
    try:
        await verify_db_connection()
        logger.info("DB 연결 확인 완료")
    except Exception as exc:
        logger.warning("DB 연결에 실패했습니다 (서버는 계속 기동): %s", exc)


async def close_db() -> None:
    """DB 엔진 종료"""
    await engine.dispose()
    logger.info("DB 엔진 종료 완료")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """DB 세션 의존성"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
