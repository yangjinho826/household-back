from fastapi import APIRouter

from app.core.api_response import ApiResponse
from app.core.auth.deps import CurrentUser
from app.domain.enum import service

router = APIRouter(prefix="/enum", tags=["enum"])


@router.get("/{name}")
async def get_enum_values(
    name: str,
    current_user: CurrentUser,  # noqa: ARG001 — 인증 가드용
) -> ApiResponse[list[str]]:
    """enum 의 모든 값을 반환.

    사용 가능한 name: account-type, category-kind, tx-type
    """
    values = service.get_enum_values(name)
    return ApiResponse.ok(data=values)
