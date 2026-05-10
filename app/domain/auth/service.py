import logging
from datetime import datetime, timedelta

from jose import ExpiredSignatureError, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.enum import TokenType
from app.core.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.core.auth.security import verify_password
from app.core.config import settings
from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.domain.auth.model import RefreshToken
from app.domain.auth.repository import RefreshTokenRepository
from app.domain.auth.schema import LoginRequest, RefreshResponse, TokenResponse
from app.domain.user.repository import UserRepository
from app.domain.user.schema import UserResponse

logger = logging.getLogger(__name__)

MAX_ACTIVE_TOKENS = 5


async def login(db: AsyncSession, req: LoginRequest) -> tuple[TokenResponse, str]:
    """로그인 처리: 사용자 검증 후 토큰 발급"""
    user_repo = UserRepository(db)
    token_repo = RefreshTokenRepository(db)

    email = req.email.strip().lower()
    user = await user_repo.find_by_email(email)
    if not user:
        logger.warning("로그인 실패 (email=%s) - 사용자 없음", email)
        raise CustomException(ErrorCode.LOGIN_FAILED)

    if user.data_stat_cd != DataStatus.ACTIVE:
        logger.warning("비활성 계정 로그인 시도 (user_id=%s)", user.id)
        raise CustomException(ErrorCode.FORBIDDEN)

    if not verify_password(req.password, user.password_hash):
        logger.warning("로그인 실패 (email=%s) - 비밀번호 불일치", email)
        raise CustomException(ErrorCode.LOGIN_FAILED)

    existing_tokens = await token_repo.find_active_by_user_id(user.id)
    if len(existing_tokens) >= MAX_ACTIVE_TOKENS:
        existing_tokens.sort(key=lambda t: t.frst_reg_dt)
        revoke_count = len(existing_tokens) - MAX_ACTIVE_TOKENS + 1
        for token_entity in existing_tokens[:revoke_count]:
            token_entity.data_stat_cd = DataStatus.DELETED
            token_entity.revoked_at = datetime.now()
        logger.info("활성 토큰 초과로 %d개 폐기 (user_id=%s)", revoke_count, user.id)

    token_data = {"sub": str(user.id), "language": user.language}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    await token_repo.save(RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=datetime.now() + timedelta(seconds=settings.JWT_REFRESH_EXPIRATION),
        data_stat_cd=DataStatus.ACTIVE,
    ))

    logger.info("로그인 성공 (user_id=%s, 활성토큰=%d개)", user.id, len(existing_tokens) + 1)

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.JWT_EXPIRATION,
        user=UserResponse.model_validate(user),
    ), refresh_token


async def refresh(db: AsyncSession, refresh_token: str) -> RefreshResponse:
    """리프레시 토큰으로 새 Access Token 발급"""
    token_repo = RefreshTokenRepository(db)

    try:
        payload = decode_token(refresh_token)
    except ExpiredSignatureError:
        logger.warning("만료된 리프레시 토큰 사용 시도")
        raise CustomException(ErrorCode.EXPIRED_TOKEN)
    except JWTError:
        logger.warning("유효하지 않은 리프레시 토큰 사용 시도")
        raise CustomException(ErrorCode.INVALID_REFRESH_TOKEN)

    if payload.get("type") != TokenType.REFRESH:
        logger.warning("잘못된 토큰 타입으로 갱신 시도 (type=%s)", payload.get("type"))
        raise CustomException(ErrorCode.INVALID_REFRESH_TOKEN)

    token_entity = await token_repo.find_active_by_token(refresh_token)
    if not token_entity:
        any_token = await token_repo.find_by_token(refresh_token)
        if any_token:
            logger.warning(
                "폐기된 리프레시 토큰 사용 시도 (user_id=%s, status=%s)",
                any_token.user_id, any_token.data_stat_cd,
            )
        else:
            logger.warning("DB에 존재하지 않는 리프레시 토큰 사용 시도")
        raise CustomException(ErrorCode.INVALID_REFRESH_TOKEN)

    token_data = {"sub": payload["sub"], "language": payload.get("language", "ko")}
    access_token = create_access_token(token_data)

    logger.info("토큰 갱신 성공 (user_id=%s)", payload["sub"])

    return RefreshResponse(
        access_token=access_token,
        expires_in=settings.JWT_EXPIRATION,
    )


async def logout(db: AsyncSession, refresh_token: str) -> None:
    """로그아웃 — DB 의 refresh token 폐기 (idempotent)"""
    token_repo = RefreshTokenRepository(db)
    token_entity = await token_repo.find_active_by_token(refresh_token)
    if token_entity:
        token_entity.data_stat_cd = DataStatus.DELETED
        token_entity.revoked_at = datetime.now()
        logger.info("로그아웃 — refresh token 폐기 (user_id=%s)", token_entity.user_id)
    else:
        logger.info("로그아웃 — DB 에 active 토큰 없음 (이미 폐기되었거나 위조)")
