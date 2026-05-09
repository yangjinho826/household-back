#!/bin/sh
# 볼륨 디렉토리 권한 설정 (root 상태에서 실행)
mkdir -p /app/logs
chown -R appuser:appuser /app/logs

# appuser로 전환하여 실행
exec gosu appuser /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
