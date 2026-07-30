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

# R2 안에서 일일 백업 전용 폴더. deploy(pre-deploy/) / rollback(pre-rollback/) 과
# 한 버킷에 섞이지 않게 daily/ 로 분리. retention 도 이 폴더에만 적용돼 서로 간섭 X.
DEST="r2:${BUCKET}/daily"

# 컨테이너 안의 pg_dump 사용 — 호스트에 postgres-client 별도 설치 불필요.
# -C/--create 를 붙이지 말 것 — 덤프 앞에 \connect 가 들어가고, restore-drill.sh 가 임시 DB 에
# 부을 때 psql 세션이 운영 DB 로 옮겨가 DDL/COPY 가 전부 운영에 떨어진다.
docker compose exec -T postgres pg_dump -U "$PG_USER" -d "$PG_DB" | gzip > "$DUMP"

rclone copy "$DUMP" "${DEST}/" --quiet
rclone delete "${DEST}/" --min-age "${RETENTION_DAYS}d" --quiet || true

rm -f "$DUMP"

echo "[$(date -Iseconds)] backup OK: ${DEST}/household-${TS}.sql.gz"
