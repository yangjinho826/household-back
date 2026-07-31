#!/usr/bin/env bash
# cron 등록 (멱등) — install.sh(최초 셋업)와 deploy.yml(매 배포 자가복구)이 공유한다.
#
# 배포마다 다시 돌리는 이유: 크론탭 유실은 조용히 일어난다(서버 교체·수동 crontab -r 실수).
# Healthchecks.io 가 "성공 ping 끊김"으로 감지(하루 안)하고, 이 스크립트가 배포 시점에
# 예방(자가복구)한다 — 감지와 예방은 잡는 구간이 달라 둘 다 필요하다.
#
# sudo 불필요 — crontab 은 유저 권한. 로그 파일(/var/log/household-*.log)은
# install.sh 1회 실행이 만들어 둔 상태를 전제한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup-db.sh"
DRILL_SCRIPT="$SCRIPT_DIR/restore-drill.sh"
LOG_FILE="/var/log/household-backup.log"
DRILL_LOG="/var/log/household-restore-drill.log"

# 배포(git reset)가 실행 권한을 벗겼던 사고 전례 — 재등록 때마다 같이 복구
chmod +x "$BACKUP_SCRIPT" "$DRILL_SCRIPT"

# 기존 라인 제거 후 재등록 — 재실행해도 중복 안 쌓임.
# 리허설은 백업 1시간 뒤 — 그날 03:00 업로드가 끝난 최신본을 대상으로 돌아야 한다.
BACKUP_CRON="0 3 * * * $BACKUP_SCRIPT >> $LOG_FILE 2>&1 # household-backup"
DRILL_CRON="0 4 * * * $DRILL_SCRIPT >> $DRILL_LOG 2>&1 # household-restore-drill"
{
  crontab -l 2>/dev/null | grep -v -e "# household-backup" -e "# household-restore-drill" || true
  echo "$BACKUP_CRON"
  echo "$DRILL_CRON"
} | crontab -
echo "[register-cron] cron 등록 완료 — 03:00 백업 / 04:00 복구 리허설 (KST)"
