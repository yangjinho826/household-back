import hashlib
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.api_response import ApiResponse
from app.core.auth.extract import extract_user_id
from app.core.database import async_session
from app.core.exceptions import CustomException
from app.core.exceptions.error_code import ErrorCode
from app.core.idempotency import service as idempotency_service
from app.core.idempotency.constants import IDEMPOTENCY_KEY_HEADER
from app.core.idempotency.response_codec import (
    build_cached_response,
    capture_response_body,
    rebuild_response,
    serialize_headers,
)

logger = logging.getLogger(__name__)


def _build_error_response(error_code: ErrorCode) -> Response:
    """CustomException → ApiResponse.fail 직렬화 (camelCase alias 포함)."""
    payload = ApiResponse.fail(
        status=error_code.status,
        code=error_code.code,
        message=error_code.message,
    )
    return Response(
        content=payload.model_dump_json(by_alias=True),
        status_code=error_code.status,
        media_type="application/json",
    )


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """POST 요청의 Idempotency-Key 헤더 기반 멱등성 처리.

    게이트 조건 (미통과 시 패스):
      - POST 메서드
      - Idempotency-Key 헤더 존재
      - 유효한 JWT (인증된 사용자)

    상태 머신:
      새 키 → PENDING INSERT (atomic ON CONFLICT DO NOTHING) → 라우터 실행
        → 성공: COMPLETED 저장
        → 실패(5xx/예외): PENDING 해제 (재시도 허용)
      COMPLETED 키 → 캐시된 응답 반환 (라우터 실행 X)
      충돌 케이스 → ID001/ID002/ID003 에러 응답
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method != "POST":
            return await call_next(request)

        key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
        if not key:
            return await call_next(request)

        user_id = extract_user_id(request)
        if not user_id:
            return await call_next(request)

        # body 캡처 + fingerprint (request body 는 한 번만 읽을 수 있으므로 재주입)
        body_bytes = await request.body()
        fingerprint = hashlib.sha256(body_bytes).hexdigest()

        path = request.url.path
        method = request.method

        async with async_session() as session:
            try:
                result = await idempotency_service.process_acquire(
                    session, user_id, key, method, path, fingerprint,
                )
            except CustomException as e:
                return _build_error_response(e.error_code)

            # 캐시 hit — DB 에서 저장된 응답 반환
            if not result.acquired and result.cached_record:
                return build_cached_response(result.cached_record)

            # 락 획득 → 라우터 실행
            try:
                response = await call_next(request)
                captured_body = await capture_response_body(response)

                if response.status_code >= 500:
                    await idempotency_service.release(session, user_id, key)
                    await session.commit()
                    return rebuild_response(response, captured_body)

                headers_json = serialize_headers(response.raw_headers)
                await idempotency_service.mark_completed(
                    session,
                    user_id,
                    key,
                    response.status_code,
                    headers_json,
                    captured_body.decode("utf-8", errors="replace"),
                )
                await session.commit()
                return rebuild_response(response, captured_body)

            except Exception:
                await idempotency_service.release(session, user_id, key)
                await session.commit()
                raise
