import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.idempotency.enums import IdempotencyStatus
from app.core.model import Base


class IdempotencyRecord(Base):
    """POST 요청의 Idempotency-Key 별 상태 + 응답 캐시.

    상태 머신: PENDING (처리 중) → COMPLETED (완료)
    PENDING row 는 락 역할 — ON CONFLICT DO NOTHING 으로 race-free 획득.
    TTL: PENDING 60초, COMPLETED 24시간 후 cleanup job 이 삭제.
    """

    __tablename__ = "idempotency_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID]
    key: Mapped[str] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    request_fingerprint: Mapped[str] = mapped_column(String(64))  # sha256(body) hex

    status: Mapped[str] = mapped_column(String(20))  # IdempotencyStatus

    # COMPLETED 시점에만 채워짐
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
        Index("ix_idempotency_status_created", "status", "created_at"),
    )

    @property
    def idempotency_status(self) -> IdempotencyStatus:
        return IdempotencyStatus(self.status)
