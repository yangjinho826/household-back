# DB 백업 (Cloudflare R2)

household PostgreSQL DB 를 매일 03:00 KST 에 Cloudflare R2 로 백업한다. 30일 이상 된 백업은 자동 삭제.

## 구성

| 파일 | 역할 |
|---|---|
| `backup-db.sh` | pg_dump → gzip → R2 업로드 → 30일 retention 적용 |
| `rclone.conf.template` | R2 자격증명 주입용 rclone 설정 템플릿 |
| `install.sh` | rclone 설치 + config 생성 + cron 등록 (1회 실행) |

## 최초 셋업

### 1. Cloudflare 측 준비 (대시보드)

- R2 버킷 생성: `household-backup` (Standard, Automatic location)
- R2 → Manage R2 API Tokens → **Create Account API token**
  - Permissions: `Object Read & Write`
  - Specify bucket: `household-backup` 만
- 발급 화면에서 다음 3개 보관 (Secret Access Key 는 그 화면 닫으면 다시 못 봄):
  - Access Key ID
  - Secret Access Key
  - Endpoint (`https://<account-id>.r2.cloudflarestorage.com`)
- (안전망) Billing → Billable usage → Create budget alert → `$1` 임계값 등록

### 2. Lightsail 호스트 셋업

```bash
ssh ubuntu@<lightsail-ip>
cd ~/household/household-back
git pull

# .env 에 R2 변수 4개 추가 (없으면 .env.example 참고)
vi .env
# R2_ACCOUNT_ID=...
# R2_ACCESS_KEY_ID=...
# R2_SECRET_ACCESS_KEY=...
# R2_BUCKET=household-backup

bash infra/backup/install.sh
```

`install.sh` 가 처리하는 것:

- `rclone`, `gettext-base` (envsubst) 설치
- `~/.config/rclone/rclone.conf` 자동 생성 (퍼미션 600)
- R2 연결 테스트 (`rclone lsd r2:household-backup`)
- `/var/log/household-backup.log` 권한 셋업
- cron 등록 (`0 3 * * *` 매일 03:00 KST)

### 3. 수동 1회 실행 (검증)

```bash
bash infra/backup/backup-db.sh
# → [2026-05-14T...] backup OK: household-2026-05-14_030000.sql.gz
```

Cloudflare 대시보드 R2 → `household-backup` 버킷에서 파일 확인.

## 복구

```bash
# 1. 백업 파일 받기
mkdir -p /tmp/restore && cd /tmp/restore
rclone copy "r2:household-backup/household-<날짜>_<시각>.sql.gz" .

# 2. 임시 DB 생성 후 restore (안전하게 검증 먼저)
docker compose exec -T postgres psql -U household -d postgres \
  -c "CREATE DATABASE household_restore_test;"

gunzip -c /tmp/restore/household-*.sql.gz | docker compose exec -T postgres \
  psql -U household -d household_restore_test

# 3. 검증
docker compose exec postgres psql -U household -d household_restore_test \
  -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public';"

# 4. 임시 DB 정리
docker compose exec postgres psql -U household -d postgres \
  -c "DROP DATABASE household_restore_test;"
```

운영 DB 직접 덮어쓰는 건 위험 — 항상 임시 DB 에 restore 해서 검증 후 데이터 옮기는 패턴 권장.

## 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| `install.sh` 가 `R2_ACCOUNT_ID 누락` 으로 종료 | `.env` 에 4개 변수 모두 채웠는지 확인 |
| `rclone lsd r2:...` 실패 | 토큰 권한 (`Object Read & Write`) 또는 버킷 범위 (`household-backup` 한정) 잘못. R2 대시보드에서 토큰 재발급 |
| `docker compose exec postgres pg_dump` 가 멈춤 | postgres 컨테이너 안 떠있음 — `docker compose ps` 확인 |
| 다음 날 백업 로그 없음 | `crontab -l` 로 `# household-backup` 라인 확인. 없으면 `install.sh` 재실행 |
| R2 비용 알림 메일 옴 | 즉시 `rclone size r2:household-backup` 로 사용량 확인. 30일 retention 안 도는지 점검 |

## 변경 시 주의

- 백업 빈도/시간 변경: `install.sh` 의 `CRON_LINE` 의 `0 3 * * *` 부분 수정 후 재실행
- retention 기간 변경: `backup-db.sh` 의 `RETENTION_DAYS=30` 수정
- 버킷 이름 변경: `.env` 의 `R2_BUCKET` 만 갱신하면 됨 (스크립트 코드 변경 X)
