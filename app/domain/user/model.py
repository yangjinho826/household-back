from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums.data_status import DataStatus
from app.core.model import BaseEntity


class User(BaseEntity):
    """사용자 엔티티"""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="ko")

    def update(
        self,
        name: str | None = None,
        password_hash: str | None = None,
        language: str | None = None,
    ) -> None:
        """사용자 정보 수정 (None인 필드는 건너뜀)"""
        if name is not None:
            self.name = name
        if password_hash is not None:
            self.password_hash = password_hash
        if language is not None:
            self.language = language

    def soft_delete(self) -> None:
        """소프트 삭제 (data_stat_cd를 DELETED로 변경)"""
        self.data_stat_cd = DataStatus.DELETED
