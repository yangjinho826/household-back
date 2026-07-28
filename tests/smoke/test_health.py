"""⓪ 환경 검증용 smoke — 이게 통과하면 테스트 실험실(env 주입·모델 스키마 생성·
session 루프 통일·ASGITransport 클라이언트)이 살아있다는 뜻.

테스트를 2개 둔 이유: 세션 전역 앱 engine 의 커넥션 풀이 테스트 사이에서 재사용될 때
이벤트 루프 바인딩이 깨지지 않는지(async 테스트의 고전적 함정) 확인하려면 최소 2개가 필요.
"""

from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import async_session


async def test_health_200(client: AsyncClient):
    # when
    response = await client.get("/health")

    # then — DB 연결(verify_db_connection)이 테스트 PG 로 붙어야 200
    assert response.status_code == 200


async def test_db_왕복(db):
    # 앱 engine/세션이 테스트 PG 로 실제 쿼리를 왕복하는지 (2번째 테스트 = 루프 재사용 검증)
    result = await db.execute(text("SELECT 1"))
    assert result.scalar_one() == 1


async def test_스키마_생성됨():
    # create_all 이 핵심 테이블을 실제로 만들었는지 — 멱등성/거래 실증의 전제
    async with async_session() as session:
        rows = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'",
            ),
        )
        tables = {r[0] for r in rows}
    assert "idempotency_records" in tables   # init.sql 엔 없던 테이블 — 모델 소스 증명
    assert "transactions" in tables
