import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.auth.jwt import decode_token

logger = logging.getLogger("app.access")

# `root_path="/api"` 가 적용된 환경에서 헬스체크 실제 path 는 `/api/health`.
# endswith 매칭으로 root_path 유무 모두 커버.
_HEALTH_PATHS: tuple[str, ...] = ("/health",)


def _extract_user_id(request: Request) -> str:
    """Authorization 헤더에서 JWT 디코드해 user id 추출 — 로그 전용 가벼운 호출.

    실제 인증은 Depends 계층(`get_current_active_user`)이 별도로 수행.
    여기는 토큰 위조 시 anonymous 로 표시하기 위해 검증 포함된 decode_token 을 그대로 재사용.
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return "-"
    token = auth[7:].strip()
    try:
        payload = decode_token(token)
    except Exception:
        return "-"
    return str(payload.get("sub") or "-")


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
        user_id = _extract_user_id(request)

        msg = (
            f"{request.method} {path} {response.status_code} "
            f"user={user_id} ip={client_ip} {duration_ms:.0f}ms"
        )

        if _is_health_path(path):
            logger.debug(msg)
        else:
            logger.info(msg)

        return response
