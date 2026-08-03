"""다중 인스턴스 실증용 자식 프로세스 — uvicorn 앱 인스턴스 1개를 띄운다.

기존 동시성 테스트(A11/B6)는 `ASGITransport` 라 한 프로세스·한 이벤트 루프 안의
경합이었다. 이 엔트리는 앱을 **별도 OS 프로세스**로 띄워 커넥션 풀·이벤트 루프·
프로세스 메모리가 분리된 상태에서의 경합을 만든다.

부모(pytest)가 `env=os.environ.copy()` 로 환경을 통째로 넘긴다. conftest.py 최상단이
`.env.test` 를 os.environ 에 덮어쓴 뒤 app 을 import 하므로 자식도 같은 테스트 DB·
같은 JWT_SECRET 을 본다 (pydantic-settings 는 환경변수가 .env 파일보다 우선).

사용: python -u -m tests.multi_instance.run_instance <port>
"""
import asyncio
import os
import sys

if sys.platform == "win32":
    # asyncpg 는 기본 Proactor 루프에서 커넥션 정리가 깨진다 (conftest 와 동일 대응).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 자식이 운영 DB 에 붙는 참사를 부모와 별개로 한 번 더 차단한다.
# conftest 는 부모 프로세스만 지켜주고, 이 프로세스는 conftest 를 타지 않는다.
_DB_URL = os.environ.get("DATABASE_URL", "")
if "test_household" not in _DB_URL:
    raise SystemExit(f"테스트 DB 가 아니다 — 기동 중단: {_DB_URL!r}")

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(sys.argv[1]),
        # 자체 AccessLogMiddleware 가 stdout 에 요청 로그를 찍는다 — uvicorn 기본 access
        # 로그는 중복이라 끈다(운영 entrypoint 의 --no-access-log 와 같은 이유).
        access_log=False,
        log_level="info",
    )
