#!/usr/bin/env bash
# household DB 일일 백업 — pg_dump → gzip → Cloudflare R2 업로드 → 30일 이상 자동 삭제.
# install.sh 가 cron 에 매일 03:00 KST 로 등록한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RETENTION_DAYS=30

# .env 로드 (POSTGRES_USER, POSTGRES_DB, R2_BUCKET)
set -a
# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"
set +a

BUCKET="${R2_BUCKET:?R2_BUCKET 환경변수가 .env 에 없음}"
PG_USER="${POSTGRES_USER:?POSTGRES_USER 환경변수가 .env 에 없음}"
PG_DB="${POSTGRES_DB:?POSTGRES_DB 환경변수가 .env 에 없음}"

cd "$PROJECT_DIR"
TS=$(date +%Y-%m-%d_%H%M%S)
DUMP="/tmp/household-${TS}.sql.gz"

# 컨테이너 안의 pg_dump 사용 — 호스트에 postgres-client 별도 설치 불필요.
docker compose exec -T postgres pg_dump -U "$PG_USER" -d "$PG_DB" | gzip > "$DUMP"

rclone copy "$DUMP" "r2:${BUCKET}/" --quiet
rclone delete "r2:${BUCKET}/" --min-age "${RETENTION_DAYS}d" --quiet || true

rm -f "$DUMP"

echo "[$(date -Iseconds)] backup OK: household-${TS}.sql.gz"
