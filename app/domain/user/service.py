from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.security import hash_password
from app.core.enums.data_status import DataStatus
from app.core.exceptions import CustomException, ErrorCode
from app.domain.user.model import User
from app.domain.user.repository import UserRepository
from app.domain.user.schema import UserCreateRequest, UserResponse, UserUpdateRequest


async def create_user(db: AsyncSession, req: UserCreateRequest) -> User:
    repo = UserRepository(db)

    email = req.email.strip().lower()
    name = req.name.strip()

    if await repo.find_by_email(email):
        raise CustomException(ErrorCode.USER_DUPLICATE_EMAIL)

    user = User(
        email=email,
        name=name,
        password_hash=hash_password(req.password),
        language=req.language,
        data_stat_cd=DataStatus.ACTIVE,
    )
    await repo.save(user)
    return user


async def detail_user(db: AsyncSession, user_id: UUID) -> UserResponse:
    repo = UserRepository(db)
    user = await repo.find_by_id(user_id)
    if not user:
        raise CustomException(ErrorCode.NOT_FOUND)
    return UserResponse.model_validate(user)


async def update_user(
    db: AsyncSession,
    user_id: UUID,
    req: UserUpdateRequest,
    current_user: User,
) -> UserResponse:
    if user_id != current_user.id:
        raise CustomException(ErrorCode.FORBIDDEN)

    repo = UserRepository(db)
    user = await repo.find_by_id(user_id)
    if not user:
        raise CustomException(ErrorCode.NOT_FOUND)

    name = req.name.strip() if req.name is not None else None
    password_hash = hash_password(req.password) if req.password is not None else None

    user.update(name=name, password_hash=password_hash, language=req.language)
    await db.flush()
    return UserResponse.model_validate(user)
