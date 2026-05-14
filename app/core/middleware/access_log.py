import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

logger = logging.getLogger("app.access")

# root_path="/api" 적용 환경과 직접 경로 둘 다 매칭. endswith 는 /api/foo/health 같은
# 무관한 경로도 잡을 위험이 있어 정확 매칭으로 좁힘.
_HEALTH_PATHS: frozenset[str] = frozenset({"/health", "/api/health"})


def _extract_user_id(request: Request) -> str:
    """`get_current_user` Depends 가 박아둔 request.state.user_id 를 읽기만.

    토큰 검증은 Depends 가 단독으로 — middleware 는 결과만 활용.
    인증 미통과(public, 401) 요청은 state 가 비어 자연스럽게 '-' 로 떨어짐.
    """
    return getattr(request.state, "user_id", None) or "-"


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

        msg = (
            f"{request.method} {path} {response.status_code} "
            f"user={_extract_user_id(request)} ip={client_ip} {duration_ms:.0f}ms"
        )

        if path in _HEALTH_PATHS:
            logger.debug(msg)
        else:
            logger.info(msg)

        return response
