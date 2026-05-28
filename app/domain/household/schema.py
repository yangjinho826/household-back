from datetime import date, datetime
from uuid import UUID

from pydantic import model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.pagination import CursorPage
from app.core.schema import CamelBaseModel
from app.domain.household.enum import HouseholdRole


class HouseholdCreateRequest(CamelBaseModel):
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


class HouseholdUpdateRequest(CamelBaseModel):
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


class HouseholdResponse(CamelBaseModel):
    id: UUID
    name: str
    description: str | None
    owner_id: UUID
    currency: str
    started_at: date
    role: HouseholdRole



class HouseholdMemberResponse(CamelBaseModel):
    id: UUID
    household_id: UUID
    user_id: UUID
    user_name: str | None = None
    user_email: str | None = None
    role: HouseholdRole
    joined_at: datetime



class HouseholdMemberCreateRequest(CamelBaseModel):
    user_id: UUID
    role: HouseholdRole = HouseholdRole.MEMBER

    @model_validator(mode="after")
    def _validate(self) -> "HouseholdMemberCreateRequest":
        if self.role == HouseholdRole.OWNER:
            # OWNER 추가는 household 생성 시에만 자동으로. API 로 OWNER 추가 X
            raise CustomException(ErrorCode.BAD_REQUEST)
        return self


# 모든 list 응답은 CursorPage 봉투로 통일. household / members 는 작은 list 라
# cursor 페이징 의미 없지만 형식만 맞춤 (next_cursor=None, has_next=False).
HouseholdListResponse = CursorPage[HouseholdResponse]
HouseholdMemberListResponse = CursorPage[HouseholdMemberResponse]
