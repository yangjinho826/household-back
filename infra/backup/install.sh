#!/usr/bin/env bash
# 백업 셋업 1회 실행 스크립트.
# - rclone 미설치면 설치
# - .env 의 R2_* 자격증명으로 ~/.config/rclone/rclone.conf 생성
# - cron 에 매일 03:00 KST 백업 + 04:00 KST 복구 리허설 등록 (이미 있으면 갱신)
#
# 실행: cd household-back && bash infra/backup/install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup-db.sh"
DRILL_SCRIPT="$SCRIPT_DIR/restore-drill.sh"
LOG_FILE="/var/log/household-backup.log"
DRILL_LOG="/var/log/household-restore-drill.log"

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

# 호스트 timezone KST 보장 — cron `0 3 * * *` 과 파일명 `date +%Y-%m-%d_...` 모두 KST 기준이어야 함.
# Lightsail Ubuntu 기본은 UTC 라 그대로면 cron 03:00 이 KST 12:00 에 실행되고 파일명도 전날로 찍힘.
CURRENT_TZ=$(timedatectl show -p Timezone --value 2>/dev/null || echo "unknown")
if [[ "$CURRENT_TZ" != "Asia/Seoul" ]]; then
  echo "[install] 호스트 timezone 변경: $CURRENT_TZ → Asia/Seoul"
  sudo timedatectl set-timezone Asia/Seoul
else
  echo "[install] 호스트 timezone 이미 Asia/Seoul"
fi

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
for f in "$LOG_FILE" "$DRILL_LOG"; do
  sudo touch "$f"
  sudo chown "$USER" "$f"
done

# 6. cron 등록 — register-cron.sh 로 분리 (deploy.yml 도 매 배포마다 같은 스크립트로 자가복구)
bash "$SCRIPT_DIR/register-cron.sh"

# 7. 장애 알림 ping URL 확인 — 없어도 백업은 돌아야 하니 경고만
if [[ -z "${HC_PING_URL_BACKUP:-}" || -z "${HC_PING_URL_DRILL:-}" ]]; then
  echo "[install] ⚠ HC_PING_URL_BACKUP / HC_PING_URL_DRILL 이 .env 에 없음 —"
  echo "          백업·리허설이 조용히 실패해도 알림이 안 간다. infra/backup/README.md 알림 섹션 참고."
fi

echo
echo "셋업 완료. 다음으로 수동 1회 실행해서 검증:"
echo "  bash $BACKUP_SCRIPT      # 백업"
echo "  bash $DRILL_SCRIPT       # 복구 리허설 — RTO 숫자가 여기서 나온다"
