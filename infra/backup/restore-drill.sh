#!/usr/bin/env bash
# 복구 리허설 — R2 daily 백업의 최신본을 임시 DB 에 복구해 검증하고 소요 시간(RTO)을 남긴다.
#
# backup-db.sh 는 "파일이 R2 에 올라갔다"까지만 증명한다. 덤프 내용이 깨졌는지는 알 수 없어서
# 사고가 터져 복구를 시도하는 순간에야 발견된다. 이 스크립트가 그 발견 시점을 최대 1일로 당긴다.
#
# 운영 DB 는 건드리지 않는다 — 임시 DB 생성 → 복구 → 검증 → drop 까지만.
# 실제 사고 시 운영 DB 롤백(swap) 절차는 별도: infra/backup/README.md 복구 섹션.
#
# install.sh 가 cron 에 매일 04:00 KST 로 등록한다. 수동 실행: bash infra/backup/restore-drill.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

DRILL_DB="household_restore_drill"
MIN_TABLES=10             # 도메인 테이블 10개(users/households/accounts/categories/transactions/
                          # fixed_expenses/portfolio_items/account_snapshots/portfolio_value_history/
                          # household_members). alembic_version 등 포함 실측 17 → 하한선으로 10
DISK_SAFETY_FACTOR=20     # 임시 DB 가 운영과 같은 pgdata 볼륨에 생긴다. gzip 덤프의 복구 후 팽창 여유분

# .env 로드 (POSTGRES_USER, R2_BUCKET)
set -a
# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"
set +a

BUCKET="${R2_BUCKET:?R2_BUCKET 환경변수가 .env 에 없음}"
PG_USER="${POSTGRES_USER:?POSTGRES_USER 환경변수가 .env 에 없음}"

cd "$PROJECT_DIR"
SRC="r2:${BUCKET}/daily"
WORK_DIR="$(mktemp -d)"

fail() {
  echo "[$(date -Iseconds)] drill FAILED: $1" >&2
  exit 1
}

# 실패로 중단돼도 임시 DB 가 남아 디스크를 먹지 않게 항상 정리
cleanup() {
  docker compose exec -T postgres psql -U "$PG_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS ${DRILL_DB} WITH (FORCE);" >/dev/null 2>&1 || true
  docker compose exec -T postgres rm -f /tmp/drill.sql.gz >/dev/null 2>&1 || true
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

# 임시 DB 를 만들 psql 이 살아있는지 먼저 — 컨테이너가 죽은 걸 restore 실패로 오인하지 않게
docker compose exec -T postgres pg_isready -U "$PG_USER" >/dev/null 2>&1 \
  || fail "postgres 컨테이너 응답 없음 (docker compose ps 확인)"

# ── 1. 최신 백업 선택 ──
# 파일명이 household-YYYY-MM-DD_HHMMSS 라 사전순 정렬 = 시간순.
# 각 캡처에 || fail 을 붙인다 — VAR=$(cmd) 는 errexit 대상이라 안 붙이면 로그에 아무 줄도 안 남고 죽는다.
LATEST=$(rclone lsf "${SRC}/" --include "household-*.sql.gz" | sort | tail -1) \
  || fail "rclone lsf 실패 — R2 자격증명/네트워크 확인"
[[ -n "$LATEST" ]] || fail "${SRC} 에 백업 파일 없음 (rclone 설정 또는 backup-db.sh 확인)"

# 백업이 멈춘 걸 복구 성공만으로는 알 수 없다 — 3주 전 덤프도 멀쩡히 복구되니 매일 OK 가 찍힌다.
# 파일명 날짜는 00:00 기준이라 그날 03:00 백업을 04:00 에 보면 4h, 하루 빠지면 28h → 26h 로 가른다.
FILE_DATE=${LATEST#household-}
FILE_DATE=${FILE_DATE%%_*}
BACKUP_AGE_H=$(( ( $(date +%s) - $(date -d "$FILE_DATE" +%s) ) / 3600 ))
[[ "$BACKUP_AGE_H" -le 26 ]] \
  || fail "최신 백업이 ${BACKUP_AGE_H}시간 전 (${LATEST}) — backup-db.sh cron 확인"

START=$(date +%s)   # RTO 측정 시작 — 실제 복구도 "R2 에서 받기"부터 시작한다

rclone copy "${SRC}/${LATEST}" "$WORK_DIR/" --quiet || fail "R2 다운로드 실패: ${LATEST}"
DUMP="$WORK_DIR/$LATEST"
DUMP_BYTES=$(stat -c %s "$DUMP") || fail "받은 덤프 크기 확인 실패: ${DUMP}"
[[ "$DUMP_BYTES" -gt 0 ]] || fail "받은 덤프가 0바이트: ${LATEST}"

# ── 2. 디스크 여유 확인 ──
NEEDED_KB=$(( DUMP_BYTES / 1024 * DISK_SAFETY_FACTOR ))
DOCKER_ROOT=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/")
AVAIL_KB=$(df -Pk "$DOCKER_ROOT" | awk 'NR==2 {print $4}') || fail "df 실패: $DOCKER_ROOT"
# 빈 값이면 [[ -gt ]] 가 조용히 false 라 "여유 0MB" 오진이 뜬다 → 파싱 실패를 따로 구분
[[ "$AVAIL_KB" =~ ^[0-9]+$ ]] || fail "df 출력 파싱 실패: [$AVAIL_KB] ($DOCKER_ROOT)"
[[ "$AVAIL_KB" -gt "$NEEDED_KB" ]] \
  || fail "디스크 부족 — 필요 약 $((NEEDED_KB/1024))MB, 여유 $((AVAIL_KB/1024))MB ($DOCKER_ROOT)"

# ── 3. 임시 DB 생성 ──
# UTF8 + template0 명시 — 이게 빠지면 복구는 성공해도 한글이 깨진다
docker compose exec -T postgres psql -U "$PG_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS ${DRILL_DB} WITH (FORCE);" >/dev/null
docker compose exec -T postgres psql -U "$PG_USER" -d postgres \
  -c "CREATE DATABASE ${DRILL_DB} OWNER ${PG_USER} ENCODING 'UTF8' TEMPLATE template0;" >/dev/null

# ── 4. 복구 ──
# 호스트 셸 파이프(gunzip -c | psql)를 거치면 셸 인코딩에 따라 한글이 ? 로 치환된다.
# 파일을 컨테이너로 옮기고 압축 해제·적용을 컨테이너 안에서 실행해 호스트 OS 영향을 없앤다.
docker compose cp "$DUMP" postgres:/tmp/drill.sql.gz >/dev/null \
  || fail "컨테이너로 덤프 복사 실패"

# 안쪽 셸에 pipefail 을 다시 켜는 게 핵심 — bash -c 는 호스트의 set -o pipefail 을 상속하지 않아서
# 없으면 gzip 종료코드(CRC/길이 검증)가 버려지고 psql 것만 남는다. psql 은 COPY 중 EOF 를 정상
# 종료로 취급하므로 ON_ERROR_STOP=1 도 잘린 덤프를 못 잡는다 → 반쯤 받아온 덤프가 OK 로 통과.
if ! docker compose exec -T postgres bash -c \
      "set -o pipefail; gzip -dc /tmp/drill.sql.gz | psql -q -U '${PG_USER}' -d '${DRILL_DB}' -v ON_ERROR_STOP=1" \
      >"$WORK_DIR/restore.log" 2>&1; then
  tail -20 "$WORK_DIR/restore.log" >&2
  fail "psql 복구 실패 — 위 로그 참조"
fi

# ── 5. 검증 ──
query() {
  docker compose exec -T postgres psql -U "$PG_USER" -d "$DRILL_DB" -t -A -c "$1" | tr -d '[:space:]'
}

TABLE_COUNT=$(query "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';") \
  || fail "테이블 수 조회 실패 (psql)"
[[ "$TABLE_COUNT" -ge "$MIN_TABLES" ]] \
  || fail "테이블 ${TABLE_COUNT}개 — 최소 ${MIN_TABLES}개 기대 (스키마만 복구됐거나 덤프가 부분적)"

# 테이블이 아예 없는 부분 복구면 psql 이 실패한다 — || fail 없으면 그 경로가 무성 종료
USER_COUNT=$(query "SELECT COUNT(*) FROM users;") || fail "users 조회 실패 — 테이블 누락 의심"
TX_COUNT=$(query "SELECT COUNT(*) FROM transactions;") || fail "transactions 조회 실패 — 테이블 누락 의심"
[[ "$USER_COUNT" -gt 0 ]] || fail "users 0행 — 데이터 없이 스키마만 복구됨"

# 한글이 ? 로 치환되는 인코딩 손상은 row 수·에러 로그로는 안 잡힌다. 직접 확인하는 유일한 방법.
# DB 안에서 정규식을 돌려 호스트 셸 인코딩을 경유하지 않는다.
# 전제: users.name 에 한글 이름이 최소 1행 존재한다. 그 전제가 깨지면(영문 이름만 남으면)
# 멀쩡한 백업에 이 assert 가 오탐을 낸다 — README 검증 항목에 전제를 명시해둠.
HANGUL_ROWS=$(query "SELECT COUNT(*) FROM users WHERE name ~ '[가-힣]';") || fail "한글 검증 조회 실패"
[[ "$HANGUL_ROWS" -gt 0 ]] || fail "users.name 에 한글 0행 — UTF8 인코딩 손상 의심"

# 데이터 시점 기록용. 백업 자체의 신선도는 위 BACKUP_AGE_H 가 assert 로 이미 막는다
LATEST_TX=$(query "SELECT COALESCE(MAX(last_mdfcn_dt)::date::text, 'none') FROM transactions;") \
  || fail "latest_tx 조회 실패"

ELAPSED=$(( $(date +%s) - START ))   # 임시 DB drop 은 복구 시간이 아니므로 여기서 끊는다

echo "[$(date -Iseconds)] drill OK: ${LATEST} ($((DUMP_BYTES / 1024 / 1024))MB) —" \
     "tables=${TABLE_COUNT} users=${USER_COUNT} transactions=${TX_COUNT}" \
     "hangul_ok latest_tx=${LATEST_TX} RTO=${ELAPSED}s"
