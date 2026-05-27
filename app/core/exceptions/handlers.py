import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.api_response import ApiResponse
from app.core.exceptions.custom_exception import CustomException
from app.core.exceptions.error_code import ErrorCode

logger = logging.getLogger(__name__)


# HTTP status → 표준 ErrorCode 매핑.
# StarletteHTTPException / 글로벌 핸들러가 임의 status 를 받았을 때 ko.json 과
# 매핑 가능한 표준 code 로 응답하기 위한 테이블. 미매핑 status 는 CM001 fallback.
_STATUS_TO_ERROR_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    500: ErrorCode.INTERNAL_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


def _error_code_for_status(status_code: int) -> ErrorCode:
    return _STATUS_TO_ERROR_CODE.get(status_code, ErrorCode.BAD_REQUEST)


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
        """HTTP 예외 처리 (Starlette 내부 예외 포함)

        starlette 의 exc.detail 은 영문이라 그대로 노출하면 프론트 토스트가 영어로 뜸.
        status 를 표준 ErrorCode 로 매핑해 프론트 ko.json 매핑이 가능하도록 한다.
        starlette detail 은 서버 로그에만 남기고, 응답 message 는 한국어 표준 메시지.
        """
        error_code = _error_code_for_status(exc.status_code)
        logger.info(
            "http exception on %s %s: status=%s detail=%s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse.fail(
                status=exc.status_code,
                code=error_code.code,
                message=error_code.message,
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """요청 유효성 검사 예외 처리

        Pydantic 기본 msg 는 영어("value is not a valid email address" 등) 라
        프론트 토스트에 그대로 뜨면 영어가 노출됨. 응답 message 는 항상
        한국어 표준 메시지(BAD_REQUEST) 로 통일하고, 구체적인 필드/원인은
        서버 로그에만 남긴다. 필드별 상세 안내가 필요하면 도메인 검증에서
        CustomException(ErrorCode.X) 으로 명시 던질 것.
        """
        errors = exc.errors()
        logger.warning(
            "validation error on %s %s: %s", request.method, request.url.path, errors
        )
        return JSONResponse(
            status_code=ErrorCode.BAD_REQUEST.status,
            content=ApiResponse.fail(
                status=ErrorCode.BAD_REQUEST.status,
                code=ErrorCode.BAD_REQUEST.code,
                message=ErrorCode.BAD_REQUEST.message,
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
