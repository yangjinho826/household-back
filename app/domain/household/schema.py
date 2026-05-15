from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.domain.household.enum import HouseholdRole


class HouseholdCreateRequest(BaseModel):
    name: str
    description: str | None = None
    started_at: date | None = None

    @model_validator(mode="after")
    def _validate(self) -> "HouseholdCreateRequest":
        if not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class HouseholdUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    started_at: date | None = None

    @model_validator(mode="after")
    def _validate(self) -> "HouseholdUpdateRequest":
        if self.name is not None and not (1 <= len(self.name.strip()) <= 100):
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


class HouseholdResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    owner_id: UUID
    started_at: date
    role: HouseholdRole

    model_config = {"from_attributes": True}


class HouseholdMemberResponse(BaseModel):
    id: UUID
    household_id: UUID
    user_id: UUID
    user_name: str | None = None
    user_email: str | None = None
    role: HouseholdRole
    joined_at: datetime

    model_config = {"from_attributes": True}


class HouseholdMemberCreateRequest(BaseModel):
    user_id: UUID
    role: HouseholdRole = HouseholdRole.MEMBER

    @model_validator(mode="after")
    def _validate(self) -> "HouseholdMemberCreateRequest":
        if self.role == HouseholdRole.OWNER:
            # OWNER 추가는 household 생성 시에만 자동으로. API 로 OWNER 추가 X
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self
