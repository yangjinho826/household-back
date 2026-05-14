#!/usr/bin/env bash
# 백업 셋업 1회 실행 스크립트.
# - rclone 미설치면 설치
# - .env 의 R2_* 자격증명으로 ~/.config/rclone/rclone.conf 생성
# - cron 에 매일 03:00 KST 백업 등록 (이미 있으면 갱신)
#
# 실행: cd household-back && bash infra/backup/install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup-db.sh"
LOG_FILE="/var/log/household-backup.log"

# 1. .env 검증
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo "ERROR: $PROJECT_DIR/.env 없음. .env.example 참고해서 만들고 R2_* 변수까지 채워줘." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"
set +a

: "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID 누락}"
: "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID 누락}"
: "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY 누락}"
: "${R2_BUCKET:?R2_BUCKET 누락}"

# 2. rclone 설치
if ! command -v rclone >/dev/null 2>&1; then
  echo "[install] rclone 설치"
  sudo apt-get update -qq
  sudo apt-get install -y -qq rclone
fi

# envsubst 가 필요 (gettext-base 패키지)
if ! command -v envsubst >/dev/null 2>&1; then
  echo "[install] gettext-base 설치 (envsubst)"
  sudo apt-get install -y -qq gettext-base
fi

# 3. rclone config 생성
RCLONE_CONF_DIR="$HOME/.config/rclone"
RCLONE_CONF="$RCLONE_CONF_DIR/rclone.conf"
mkdir -p "$RCLONE_CONF_DIR"
chmod 700 "$RCLONE_CONF_DIR"

envsubst < "$SCRIPT_DIR/rclone.conf.template" > "$RCLONE_CONF"
chmod 600 "$RCLONE_CONF"
echo "[install] rclone config 생성: $RCLONE_CONF"

# 4. 연결 테스트
if ! rclone lsd "r2:${R2_BUCKET}" >/dev/null 2>&1; then
  echo "ERROR: r2:${R2_BUCKET} 접근 실패 — 자격증명/버킷명 확인" >&2
  exit 1
fi
echo "[install] R2 연결 OK"

# 5. 로그 파일 권한
sudo touch "$LOG_FILE"
sudo chown "$USER" "$LOG_FILE"

# 6. cron 등록 (기존 household-backup 라인 제거 후 재등록)
CRON_LINE="0 3 * * * $BACKUP_SCRIPT >> $LOG_FILE 2>&1 # household-backup"
( crontab -l 2>/dev/null | grep -v "# household-backup" ; echo "$CRON_LINE" ) | crontab -
echo "[install] cron 등록 완료 — 매일 03:00 KST 백업"

chmod +x "$BACKUP_SCRIPT"

echo
echo "셋업 완료. 다음으로 수동 1회 실행해서 검증:"
echo "  bash $BACKUP_SCRIPT"
