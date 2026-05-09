import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.api_response import ApiResponse
from app.core.exceptions.custom_exception import CustomException
from app.core.exceptions.error_code import ErrorCode

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """모든 예외 핸들러를 앱에 등록"""

    @app.exception_handler(CustomException)
    async def custom_exception_handler(
        request: Request, exc: CustomException
    ) -> JSONResponse:
        """비즈니스 예외 처리"""
        return JSONResponse(
            status_code=exc.error_code.status,
            content=ApiResponse.fail(
                status=exc.error_code.status,
                code=exc.error_code.code,
                message=exc.message,
            ).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """HTTP 예외 처리 (Starlette 내부 예외 포함)"""
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse.fail(
                status=exc.status_code,
                code=f"CM{exc.status_code}",
                message=str(exc.detail),
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """요청 유효성 검사 예외 처리"""
        errors = exc.errors()
        message = (
            errors[0].get("msg", "잘못된 요청입니다.") if errors else "잘못된 요청입니다."
        )
        return JSONResponse(
            status_code=400,
            content=ApiResponse.fail(
                status=400,
                code=ErrorCode.BAD_REQUEST.code,
                message=message,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """처리되지 않은 예외 처리"""
        logger.exception("처리되지 않은 예외 발생: %s", exc)
        return JSONResponse(
            status_code=500,
            content=ApiResponse.fail(
                status=500,
                code=ErrorCode.INTERNAL_ERROR.code,
                message=ErrorCode.INTERNAL_ERROR.message,
            ).model_dump(),
        )
