from fastapi import APIRouter

from app.core.api_response import ApiResponse
from app.core.database import verify_db_connection
from app.core.exceptions import CustomException, ErrorCode

router = APIRouter()


@router.get("/health")
async def health_check() -> ApiResponse:
    """서버 상태 확인 (DB 연결 포함)"""
    try:
        await verify_db_connection()
    except Exception:
        raise CustomException(ErrorCode.SERVICE_UNAVAILABLE)
    return ApiResponse.ok()
