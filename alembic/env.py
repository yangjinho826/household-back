import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.config import settings
from app.core.model import Base

# 모든 도메인 모델을 import — Base.metadata 에 등록
from app.domain.account.model import Account  # noqa: F401
from app.domain.account_snapshot.model import AccountSnapshot  # noqa: F401
from app.domain.auth.model import RefreshToken  # noqa: F401
from app.domain.category.model import Category  # noqa: F401
from app.domain.fixed.model import FixedExpense  # noqa: F401
from app.domain.household.model import Household, HouseholdMember  # noqa: F401
from app.domain.portfolio.model import (  # noqa: F401
    PortfolioItem,
    PortfolioTransaction,
    PortfolioValueHistory,
)
from app.domain.transaction.model import Transaction  # noqa: F401
from app.domain.user.model import User  # noqa: F401

config = context.config

# runtime 에 DATABASE_URL 주입
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
