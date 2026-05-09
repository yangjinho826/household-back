from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_response import ApiResponse
from app.core.auth.deps import CurrentUser
from app.core.database import get_db
from app.domain.user import service
from app.domain.user.schema import UserCreateRequest, UserResponse, UserUpdateRequest

router = APIRouter(prefix="/user", tags=["user"])


@router.post("")
async def create(
    req: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserResponse]:
    """회원 가입"""
    user = await service.create_user(db, req)
    return ApiResponse.ok(data=UserResponse.model_validate(user))


@router.get("/{user_id}")
async def detail(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserResponse]:
    """사용자 상세 조회"""
    response = await service.detail_user(db, user_id)
    return ApiResponse.ok(data=response)


@router.put("/{user_id}")
async def update(
    user_id: UUID,
    req: UserUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserResponse]:
    """사용자 정보 수정 (본인만 가능)"""
    response = await service.update_user(db, user_id, req, current_user)
    return ApiResponse.ok(data=response)
