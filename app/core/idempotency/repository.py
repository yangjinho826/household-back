import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.idempotency.constants import COMPLETED_TTL_HOURS, PENDING_TTL_SECONDS
from app.core.idempotency.enums import IdempotencyStatus
from app.core.idempotency.model import IdempotencyRecord


class IdempotencyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def try_acquire(
        self,
        user_id: uuid.UUID,
        key: str,
        method: str,
        path: str,
        fingerprint: str,
    ) -> bool:
        """PENDING row INSERT 시도. 성공(락 획득) → True, 충돌 → False.

        ON CONFLICT DO NOTHING 이 atomic 락 역할 — race condition 없음.
        """
        stmt = (
            pg_insert(IdempotencyRecord)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                key=key,
                method=method,
                path=path,
                request_fingerprint=fingerprint,
                status=IdempotencyStatus.PENDING,
                created_at=datetime.now(),
            )
            .on_conflict_do_nothing(index_elements=["user_id", "key"])
            .returning(IdempotencyRecord.id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def find(self, user_id: uuid.UUID, key: str) -> IdempotencyRecord | None:
        stmt = select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.key == key,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def mark_completed(
        self,
        user_id: uuid.UUID,
        key: str,
        status_code: int,
        headers_json: str,
        body: str,
    ) -> None:
        stmt = (
            update(IdempotencyRecord)
            .where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.key == key,
            )
            .values(
                status=IdempotencyStatus.COMPLETED,
                status_code=status_code,
                response_headers=headers_json,
                response_body=body,
                completed_at=datetime.now(),
            )
        )
        await self.db.execute(stmt)

    async def release(self, user_id: uuid.UUID, key: str) -> None:
        """락 해제 — 라우터 실패 시 PENDING row 삭제해서 재시도 허용."""
        stmt = delete(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.key == key,
            IdempotencyRecord.status == IdempotencyStatus.PENDING,
        )
        await self.db.execute(stmt)

    async def cleanup_expired(self) -> tuple[int, int]:
        """TTL 만료된 레코드 삭제. (삭제된 PENDING 수, COMPLETED 수) 반환."""
        now = datetime.now()

        pending_cutoff = now - timedelta(seconds=PENDING_TTL_SECONDS)
        pending_result = await self.db.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.status == IdempotencyStatus.PENDING,
                IdempotencyRecord.created_at < pending_cutoff,
            )
        )

        completed_cutoff = now - timedelta(hours=COMPLETED_TTL_HOURS)
        completed_result = await self.db.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.status == IdempotencyStatus.COMPLETED,
                IdempotencyRecord.completed_at < completed_cutoff,
            )
        )

        return (pending_result.rowcount or 0, completed_result.rowcount or 0)
