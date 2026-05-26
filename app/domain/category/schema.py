from uuid import UUID

from pydantic import model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.schema import CamelBaseModel
from app.domain.category.enum import CategoryKind


class CategoryListQuery(CamelBaseModel):
    """카테고리 목록 쿼리 파라미터."""

    search_term: str | None = None
    kind: CategoryKind | None = None
    is_archived: bool | None = None


class CategoryCreateRequest(CamelBaseModel):
    kind: CategoryKind
    name: str
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None

    @model_validator(mode="after")
    def _validate(self) -> "CategoryCreateRequest":
        if not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.color is not None and len(self.color) > 7:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class CategoryUpdateRequest(CamelBaseModel):
    kind: CategoryKind | None = None
    name: str | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None
    is_archived: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> "CategoryUpdateRequest":
        if self.name is not None and not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.color is not None and len(self.color) > 7:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class CategoryResponse(CamelBaseModel):
    id: UUID
    household_id: UUID
    kind: CategoryKind
    name: str
    color: str | None
    icon: str | None
    sort_order: int
    is_archived: bool
