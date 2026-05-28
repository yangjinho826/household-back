"""커서 기반 페이징 공통 컴포넌트.

모든 list endpoint 응답을 `CursorPage[T]` 봉투로 통일.
정렬 키 + UUID 평문 cursor 형식: ``f"{sort_key}|{id}"``.

- `total_count` 는 관리 페이지(검색/필터 + 총 N개 노출)에서만 채움.
- overview / 단순 무한 스크롤 응답은 `None` 으로 두고 hasNext 만 신뢰.
"""

from typing import Generic, TypeVar

from app.core.schema import CamelBaseModel

T = TypeVar("T")


class CursorPage(CamelBaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_next: bool = False
    total_count: int | None = None

    @classmethod
    def of(
        cls,
        items: list[T],
        next_cursor: str | None = None,
        has_next: bool = False,
        total_count: int | None = None,
    ) -> "CursorPage[T]":
        return cls(
            items=items,
            next_cursor=next_cursor,
            has_next=has_next,
            total_count=total_count,
        )
