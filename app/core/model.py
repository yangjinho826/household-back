import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 선언적 베이스"""
    pass


class BaseEntity(Base):
    """공통 컬럼을 가진 추상 엔티티"""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    frst_reg_dt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now,
    )
    last_mdfcn_dt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now,
    )
    data_stat_cd: Mapped[str] = mapped_column(String(30))
