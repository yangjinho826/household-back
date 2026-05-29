import uuid

from starlette.requests import Request

from app.core.auth.jwt import decode_token


def extract_user_id(request: Request) -> uuid.UUID | None:
    """Authorization 헤더에서 JWT 디코드해 user UUID 추출. 실패 시 None."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    try:
        payload = decode_token(token)
    except Exception:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        return uuid.UUID(str(sub))
    except (ValueError, TypeError):
        return None
