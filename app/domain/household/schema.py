from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.domain.household.enum import HouseholdRole


class HouseholdCreateRequest(BaseModel):
    name: str
    description: str | None = None
    currency: str = "KRW"
    started_at: date | None = None

    @model_validator(mode="after")
    def _validate(self) -> "HouseholdCreateRequest":
        if not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        if len(self.currency) != 3:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class HouseholdUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    currency: str | None = None
    started_at: date | None = None

    @model_validator(mode="after")
    def _validate(self) -> "HouseholdUpdateRequest":
        if self.name is not None and not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        if self.currency is not None and len(self.currency) != 3:
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class HouseholdResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    owner_id: UUID
    currency: str
    started_at: date
    role: HouseholdRole

    model_config = {"from_attributes": True}


class HouseholdMemberResponse(BaseModel):
    id: UUID
    household_id: UUID
    user_id: UUID
    role: HouseholdRole
    joined_at: datetime

    model_config = {"from_attributes": True}
