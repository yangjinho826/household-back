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

# ── Healthchecks.io ping (옵셔널 — URL 미설정이면 전부 no-op) ──
# 성공 시 ping 을 보내고, "ping 이 끊겼다"를 서버 밖(HC)이 감지한다(dead man's switch).
# 실패 알림을 스크립트가 직접 쏘는 구조는 cron 자체가 멈추면 같이 침묵하기 때문.
HC_URL="${HC_PING_URL_BACKUP:-}"
PINGED=0

ping_hc() {  # $1: ""|/fail  $2: 본문(선택). 알림은 보조라 실패해도 스크립트에 영향 X
  [[ -n "$HC_URL" ]] || return 0
  curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "${2:-}" "${HC_URL}${1:-}" || true
}

# trap ERR 가 아니라 EXIT 백스톱인 이유: ${VAR:?} 확장 실패는 ERR 를 안 태우고,
# 함수 안 실패는 -E 없이 ERR 상속이 안 된다. 종료 코드는 경로 불문 항상 잡힌다.
on_exit() {
  local rc=$?
  if [[ "$rc" -ne 0 && "$PINGED" -ne 1 ]]; then
    ping_hc /fail "backup 실패 exit=${rc} (로그: /var/log/household-backup.log)"
  fi
}
trap on_exit EXIT

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

MSG="backup OK: ${DEST}/household-${TS}.sql.gz"
echo "[$(date -Iseconds)] ${MSG}"
ping_hc "" "$MSG"
PINGED=1
