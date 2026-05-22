"""응답 ↔ DB row 직렬화.

헤더는 list[tuple[str, str]] JSON 으로 직렬화해 multi-value 헤더(Set-Cookie 등) 보존.
dict() 변환 금지 — multi-value 헤더가 마지막 값으로 압축됨.
"""
import json

from starlette.responses import Response

from app.core.idempotency.model import IdempotencyRecord


def serialize_headers(raw_headers: list[tuple[bytes, bytes]]) -> str:
    """ASGI raw_headers (bytes tuple list) → JSON string."""
    return json.dumps(
        [[k.decode(), v.decode()] for k, v in raw_headers],
    )


def deserialize_headers(serialized: str) -> list[tuple[str, str]]:
    return [tuple(pair) for pair in json.loads(serialized)]  # type: ignore[misc]


def build_cached_response(record: IdempotencyRecord) -> Response:
    """COMPLETED row 에서 원본 응답 재구성. multi-value 헤더 보존."""
    headers = deserialize_headers(record.response_headers or "[]")
    # starlette Response 는 headers 를 MutableHeaders 로 관리하므로
    # raw_headers 를 직접 넘기지 않고 dict 로 전달 — 단 Set-Cookie 처럼 중복이 필요한
    # 헤더는 headers 인자로는 표현 불가. raw_headers 파라미터 사용.
    response = Response(
        content=(record.response_body or "").encode(),
        status_code=record.status_code or 200,
    )
    # raw_headers 를 직접 교체해 multi-value 보존
    response.raw_headers = [
        (k.encode() if isinstance(k, str) else k, v.encode() if isinstance(v, str) else v)
        for k, v in headers
    ]
    return response


async def capture_response_body(response: Response) -> bytes:
    """StreamingResponse 의 body_iterator 소진 → bytes 반환.

    FastAPI 는 라우터 반환값을 즉시 bytes 로 변환하지 않고
    ASGI 스펙에 따라 body_iterator (async generator) 로 만듦.
    미들웨어에서 DB 저장을 위해 iterator 를 한 번 소진해야 하고,
    소진 후 새 Response 로 재구성해서 클라이언트에 전달.
    """
    body = b""
    async for chunk in response.body_iterator:  # type: ignore[union-attr]
        body += chunk
    return body


def rebuild_response(response: Response, body: bytes) -> Response:
    """캡처한 body + 원본 헤더/media_type 으로 전송용 Response 재구성."""
    rebuilt = Response(
        content=body,
        status_code=response.status_code,
        media_type=response.media_type,
    )
    rebuilt.raw_headers = response.raw_headers
    return rebuilt
