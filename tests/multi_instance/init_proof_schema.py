"""실증 스택 스키마 초기화 — 모델로 생성 후 alembic head 로 stamp.

**왜 운영과 같은 `init.sql → alembic upgrade head` 경로를 못 쓰나** (2026-08-03 실증에서 발견):
`ddl/init.sql` 은 alembic baseline(`be504a39cec0`, 빈 마이그레이션) 시점의 스냅샷이어야
하는데 이후 스키마 변경이 일부 반영돼 드리프트했다. 예를 들어 init.sql 의
`fixed_expenses` 에는 `amount` 컬럼이 없는데, 리비전 `a9668f7687a9` 는 그 컬럼을
`DROP` 하려 한다 → 빈 볼륨에서 체인이 `UndefinedColumnError` 로 끊긴다.
운영 DB 는 이미 `stamp head` 상태라 증분만 적용해 와서 이 경로를 타지 않는다.
상세: `docs/multi-instance-proof.md`

그래서 실증 스택은 conftest 와 같은 소스(런타임 SQLAlchemy 모델)로 스키마를 만들고
head 로 stamp 한다. 결과 스키마는 운영과 동등하고, 앱 컨테이너는 entrypoint 의
`alembic upgrade head` 를 그대로 타서(stamp 된 상태라 no-op) 기동 경로는 운영과 같다.
"""
import asyncio

from alembic import command
from alembic.config import Config

from app.core.database import engine
from app.core.model import Base
from app.main import app  # noqa: F401  — 전 도메인 모델을 Base.metadata 에 등록시킨다


async def _create_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


def main() -> None:
    asyncio.run(_create_schema())
    # stamp 는 env.py 를 거치며 자체 asyncio.run 을 돌린다 — 위 루프가 닫힌 뒤 호출해야 한다.
    command.stamp(Config("alembic.ini"), "head")
    print("스키마 초기화 완료 (create_all + stamp head)")


if __name__ == "__main__":
    main()
