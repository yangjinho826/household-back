from uuid import UUID

from pydantic import BaseModel, model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.domain.category.enum import CategoryKind


class CategoryCreateRequest(BaseModel):
    is_income: bool
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

    @property
    def kind(self) -> CategoryKind:
        return CategoryKind.INCOME if self.is_income else CategoryKind.EXPENSE


class CategoryUpdateRequest(BaseModel):
    is_income: bool | None = None
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


class CategoryResponse(BaseModel):
    id: UUID
    household_id: UUID
    is_income: bool
    name: str
    color: str | None
    icon: str | None
    sort_order: int
    is_archived: bool

    model_config = {"from_attributes": True}
