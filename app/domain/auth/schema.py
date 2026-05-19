import re

from pydantic import model_validator

from app.core.exceptions import CustomException, ErrorCode
from app.core.schema import CamelBaseModel
from app.domain.user.schema import UserResponse

_EMAIL_RE = re.compile(r"^[\w\.\-]+@[\w\.\-]+\.\w+$")


class LoginRequest(CamelBaseModel):
    email: str
    password: str

    @model_validator(mode="after")
    def _validate(self) -> "LoginRequest":
        if not (1 <= len(self.email) <= 255) or not _EMAIL_RE.match(self.email):
            raise CustomException(ErrorCode.INVALID_EMAIL_FORMAT)
        if not (1 <= len(self.password) <= 64):
            raise CustomException(ErrorCode.LOGIN_FAILED)
        return self


class TokenResponse(CamelBaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshResponse(CamelBaseModel):
    access_token: str
    expires_in: int
