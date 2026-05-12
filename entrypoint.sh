#!/bin/sh
# appuser로 전환하여 실행
exec gosu appuser /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
