from fastapi import APIRouter

from app.core.api_response import ApiResponse
from app.core.database import verify_db_connection
from app.core.exceptions import CustomException, ErrorCode

router = APIRouter()


# HEAD 포함 — FastAPI 는 GET 라우트에 HEAD 를 자동 지원하지 않아 405 가 난다.
# 외부 uptime 모니터(UptimeRobot free)가 HEAD 고정이라 405 면 영구 down 오탐.
@router.api_route("/health", methods=["GET", "HEAD"])
async def health_check() -> ApiResponse:
    """서버 상태 확인 (DB 연결 포함)"""
    try:
        await verify_db_connection()
    except Exception:
        raise CustomException(ErrorCode.SERVICE_UNAVAILABLE)
    return ApiResponse.ok()
