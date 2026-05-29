import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CustomException, ErrorCode
from app.core.idempotency.enums import IdempotencyStatus
from app.core.idempotency.model import IdempotencyRecord
from app.core.idempotency.repository import IdempotencyRepository

logger = logging.getLogger(__name__)


@dataclass
class AcquireResult:
    acquired: bool
    cached_record: IdempotencyRecord | None = field(default=None)


async def process_acquire(
    session: AsyncSession,
    user_id: uuid.UUID,
    key: str,
    method: str,
    path: str,
    fingerprint: str,
) -> AcquireResult:
    """PENDING 락 획득 시도 + 충돌 분기.

    Returns:
        AcquireResult(acquired=True) — 새 요청, 라우터 실행 허용
        AcquireResult(acquired=False, cached_record=row) — 캐시 hit

    Raises:
        CustomException(IDEMPOTENCY_KEY_CONFLICT) — 같은 키 다른 endpoint
        CustomException(IDEMPOTENCY_BODY_MISMATCH) — 같은 키 다른 body
        CustomException(IDEMPOTENCY_IN_PROGRESS) — 동일 요청 처리 중
    """
    repo = IdempotencyRepository(session)

    acquired = await repo.try_acquire(user_id, key, method, path, fingerprint)
    if acquired:
        logger.debug("idempotency acquire: key=%s user=%s", key, user_id)
        return AcquireResult(acquired=True)

    # 충돌 — 기존 row 조회 후 분기
    existing = await repo.find(user_id, key)

    if existing is None:
        # try_acquire 충돌 후 find 도 None — 극히 드문 race (TTL cleanup 타이밍)
        # 안전하게 IN_PROGRESS 처리
        raise CustomException(ErrorCode.IDEMPOTENCY_IN_PROGRESS)

    if existing.method != method or existing.path != path:
        raise CustomException(ErrorCode.IDEMPOTENCY_KEY_CONFLICT)

    if existing.request_fingerprint != fingerprint:
        raise CustomException(ErrorCode.IDEMPOTENCY_BODY_MISMATCH)

    if existing.idempotency_status == IdempotencyStatus.COMPLETED:
        logger.info("idempotency cache hit: key=%s user=%s", key, user_id)
        return AcquireResult(acquired=False, cached_record=existing)

    # PENDING + 같은 fingerprint → 처리 중
    logger.info("idempotency in-progress: key=%s user=%s", key, user_id)
    raise CustomException(ErrorCode.IDEMPOTENCY_IN_PROGRESS)


async def mark_completed(
    session: AsyncSession,
    user_id: uuid.UUID,
    key: str,
    status_code: int,
    headers_json: str,
    body: str,
) -> None:
    repo = IdempotencyRepository(session)
    await repo.mark_completed(user_id, key, status_code, headers_json, body)
    logger.debug("idempotency completed: key=%s user=%s status=%d", key, user_id, status_code)


async def release(session: AsyncSession, user_id: uuid.UUID, key: str) -> None:
    """실패 응답 또는 예외 시 PENDING 락 해제 → 재시도 허용."""
    repo = IdempotencyRepository(session)
    await repo.release(user_id, key)
    logger.debug("idempotency released: key=%s user=%s", key, user_id)


async def cleanup_expired(session: AsyncSession) -> None:
    """TTL 만료 레코드 삭제. 잡 스케줄러가 매시간 호출."""
    repo = IdempotencyRepository(session)
    pending, completed = await repo.cleanup_expired()
    if pending > 0 or completed > 0:
        logger.info(
            "idempotency cleanup: pending=%d completed=%d", pending, completed,
        )
