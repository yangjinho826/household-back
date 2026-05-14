#!/bin/sh
set -e

# 볼륨 디렉토리 권한 설정 (root 상태에서 실행)
mkdir -p /app/logs
chown -R appuser:appuser /app/logs

# DB 마이그레이션 적용 (appuser 권한, WORKDIR = /app)
gosu appuser /app/.venv/bin/alembic upgrade head

# appuser 로 전환하여 uvicorn 실행
# --proxy-headers: nginx 가 보내는 X-Forwarded-Proto / X-Forwarded-For / Host 신뢰
# --forwarded-allow-ips='*': 외부 노출은 nginx 만이라 와일드카드 OK
exec gosu appuser /app/.venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips='*'
