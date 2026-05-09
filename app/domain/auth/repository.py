from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums.data_status import DataStatus
from app.domain.auth.model import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_active_by_user_id(self, user_id: UUID) -> list[RefreshToken]:
        result = await self.db.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return list(result.scalars().all())

    async def find_active_by_token(self, token: str) -> RefreshToken | None:
        result = await self.db.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.token == token,
                    RefreshToken.data_stat_cd == DataStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_by_token(self, token: str) -> RefreshToken | None:
        """상태 무관하게 토큰 조회 (디버깅용)"""
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token == token)
        )
        return result.scalar_one_or_none()

    async def save(self, token: RefreshToken) -> None:
        self.db.add(token)
        await self.db.flush()
