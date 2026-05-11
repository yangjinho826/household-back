from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.user.model import User


class UserRepository:
    """사용자 데이터 접근 레포지토리"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.id == user_id,
                    User.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_by_ids(self, user_ids: list[UUID]) -> list[User]:
        if not user_ids:
            return []
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.id.in_(user_ids),
                    User.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return list(result.scalars().all())

    async def find_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.email == email,
                    User.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def save(self, user: User) -> None:
        self.db.add(user)
        await self.db.flush()
