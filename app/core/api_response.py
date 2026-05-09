from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """통일 API 응답 스키마"""

    status: int
    code: str | None = None
    message: str | None = None
    data: T | None = None

    @classmethod
    def ok(cls, data: T | None = None) -> "ApiResponse[T]":
        """성공 응답 생성

        Args:
            data: 응답 데이터 (선택)

        Returns:
            status=200, code="CM000"인 ApiResponse
        """
        return cls(status=200, code="CM000", message="성공", data=data)

    @classmethod
    def fail(cls, status: int, code: str, message: str) -> "ApiResponse[None]":
        """실패 응답 생성

        Args:
            status: HTTP 상태 코드
            code: 비즈니스 에러 코드
            message: 에러 메시지

        Returns:
            실패 정보가 담긴 ApiResponse
        """
        return cls(status=status, code=code, message=message)
