import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.auth.extract import extract_user_id

logger = logging.getLogger("app.access")

# `root_path="/api"` 가 적용된 환경에서 헬스체크 실제 path 는 `/api/health`.
# endswith 매칭으로 root_path 유무 모두 커버.
_HEALTH_PATHS: tuple[str, ...] = ("/health",)


def _is_health_path(path: str) -> bool:
    return any(path.endswith(p) for p in _HEALTH_PATHS)


class AccessLogMiddleware(BaseHTTPMiddleware):
    """요청 단위 access log 미들웨어.

    한 줄 포맷: `<METHOD> <path> <status> user=<uuid|-> ip=<ip> <ms>ms`.
    헬스체크 path 는 DEBUG 로 강등 — `LOG_LEVEL=INFO` 면 비노출.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        path = request.url.path
        client_ip = request.client.host if request.client else "-"
        user_id_obj = extract_user_id(request)
        user_id = str(user_id_obj) if user_id_obj else "-"

        msg = (
            f"{request.method} {path} {response.status_code} "
            f"user={user_id} ip={client_ip} {duration_ms:.0f}ms"
        )

        if _is_health_path(path):
            logger.debug(msg)
        else:
            logger.info(msg)

        return response
