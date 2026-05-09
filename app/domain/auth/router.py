import logging

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import CustomException, ErrorCode
from app.domain.auth import service
from app.domain.auth.schema import LoginRequest, RefreshResponse, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE_KEY = "refresh_token"
_REFRESH_COOKIE_PATH = "/"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Refresh Token을 HttpOnly 쿠키로 설정"""
    response.set_cookie(
        key=_REFRESH_COOKIE_KEY,
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="strict",
        path=_REFRESH_COOKIE_PATH,
        max_age=settings.JWT_REFRESH_EXPIRATION,
    )


def _delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_REFRESH_COOKIE_KEY, path=_REFRESH_COOKIE_PATH)


@router.post("/login")
async def login(
    req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenResponse]:
    """로그인 후 JWT 토큰 발급"""
    token_response, refresh_token = await service.login(db, req)
    _set_refresh_cookie(response, refresh_token)
    return ApiResponse.ok(data=token_response)


@router.post("/refresh")
async def refresh(
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(None, alias=_REFRESH_COOKIE_KEY),
) -> ApiResponse[RefreshResponse]:
    """Refresh Token으로 새 Access Token 발급"""
    if not refresh_token:
        logger.warning("리프레시 토큰 쿠키 없이 갱신 요청")
        raise CustomException(ErrorCode.INVALID_REFRESH_TOKEN)
    result = await service.refresh(db, refresh_token)
    return ApiResponse.ok(data=result)


@router.post("/logout")
async def logout(response: Response) -> ApiResponse[None]:
    """로그아웃 (쿠키 삭제)"""
    _delete_refresh_cookie(response)
    return ApiResponse.ok()
