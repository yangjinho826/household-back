#!/bin/sh
set -e

# 볼륨 디렉토리 권한 설정 (root 상태에서 실행)
mkdir -p /app/logs
chown -R appuser:appuser /app/logs

# DB 마이그레이션 적용 (appuser 권한, WORKDIR = /app)
gosu appuser /app/.venv/bin/alembic upgrade head

# appuser 로 전환하여 uvicorn 실행
exec gosu appuser /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
