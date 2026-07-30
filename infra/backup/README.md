# DB 백업 (Cloudflare R2)

household PostgreSQL DB 를 매일 03:00 KST 에 Cloudflare R2 로 백업한다. 30일 이상 된 백업은 자동 삭제. 이어서 04:00 에 그 백업을 임시 DB 에 복구해보는 리허설이 돌아 "복구 가능한 상태"를 매일 확인한다.

## 구성

| 파일 | 역할 |
|---|---|
| `backup-db.sh` | pg_dump → gzip → R2 업로드 → 30일 retention 적용 |
| `restore-drill.sh` | 매일 04:00 복구 리허설 — 최신 백업을 임시 DB 에 복구·검증하고 RTO 기록 |
| `rclone.conf.template` | R2 자격증명 주입용 rclone 설정 템플릿 |
| `install.sh` | rclone 설치 + config 생성 + cron 2개 등록 (1회 실행) |

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

- 호스트 timezone `Asia/Seoul` 자동 설정 (cron + 파일명 모두 KST 기준이 되도록)
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
rclone ls r2:household-backup/daily/ | sort          # 사용 가능한 백업 목록
rclone copy "r2:household-backup/daily/household-<날짜>_<시각>.sql.gz" .

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

## 복구 리허설 (`restore-drill.sh`)

위 복구 절차를 **매일 04:00 KST 에 자동으로** 돌린다. `backup-db.sh` 는 "파일이 R2 에 올라갔다"까지만 증명하고 덤프 내용이 온전한지는 모른다 — 사고가 터져 복구를 시도하는 순간에야 발견되는 구조라서, 그 발견 시점을 최대 1일로 당기는 장치.

**운영 DB 는 건드리지 않는다.** 임시 DB(`household_restore_drill`) 생성 → 복구 → 검증 → drop 까지만. 위 "복구" 섹션의 1~3단계에 해당하고, 운영 DB 를 갈아끼우는 단계는 하지 않는다.

### 검증 항목

| 항목 | 실패 의미 |
|---|---|
| 최신 백업이 26시간 이내 | **백업 cron 이 멈췄음.** 3주 전 덤프도 복구는 되니 이 검사 없으면 매일 OK 가 찍힌다 |
| `gzip -dc` 종료코드 (컨테이너 안 `set -o pipefail` 필수) | 덤프가 잘렸거나 gzip 이 깨졌음. `bash -c` 는 호스트 pipefail 을 상속하지 않고, psql 은 COPY 중 EOF 를 정상 종료로 취급해서 `ON_ERROR_STOP` 만으로는 못 잡는다 |
| `psql -v ON_ERROR_STOP=1` 통과 | SQL 레벨 에러 (제약 위반, 타입 불일치 등) |
| 테이블 ≥ 10개 | 스키마만 복구됐거나 덤프가 부분적 |
| `users` 행 > 0 | 데이터 없이 스키마만 |
| `users.name` 에 한글 행 > 0 | **UTF8 인코딩 손상** — 행 수·에러 로그로는 안 잡히는 유일한 실패 모드 |

`users.name` 한글 검사는 **한글 이름 행이 최소 1개 존재한다는 전제**에 기댄다. 전부 영문 이름으로 바뀌면 멀쩡한 백업에도 `한글 0행` 실패가 뜬다 — 그때는 검사 대상 컬럼을 바꿔야 한다. `MAX(last_mdfcn_dt)` 는 assert 가 아니라 로그 기록용(`latest_tx=`).

디스크 여유(압축 크기 × 20)도 복구 전에 확인한다 — 임시 DB 가 운영과 같은 pgdata 볼륨에 생기기 때문.

### 로그

```bash
tail -5 /var/log/household-restore-drill.log
# [2026-08-02T04:00:41+09:00] drill OK: household-2026-08-02_030001.sql.gz (12MB) —
#   tables=17 users=5 transactions=1843 hangul_ok latest_tx=2026-08-02 RTO=41s
```

`RTO=41s` = R2 다운로드부터 검증 완료까지 실측 소요 시간. 임시 DB drop 은 복구 시간이 아니라 제외.

실패 시 `drill FAILED: <이유>` 한 줄 + exit 1. **알림은 아직 없다** — 로그만 쌓이므로 직접 확인해야 한다 (장애 알림은 `docs/portfolio-sre-roadmap.md` 3번).

### 수동 실행

```bash
bash infra/backup/restore-drill.sh     # cron 안 기다리고 바로 RTO 확인
```

## 로그 확인

- `/var/log/household-backup.log` — 03:00 백업. 성공 시 `[ISO timestamp] backup OK: ...` 한 줄, 실패 시 stderr 도 같이 남음
- `/var/log/household-restore-drill.log` — 04:00 복구 리허설. `drill OK: ... RTO=Ns` 또는 `drill FAILED: <이유>`
- 실시간: `tail -f /var/log/household-backup.log`
- 마지막 N줄: `tail -100 /var/log/household-backup.log`
- R2 콘솔 `household-backup` 버킷 — 업로드된 파일 목록 자체가 두 번째 로그 역할

윈도우 PC 가 아니라 **Lightsail 호스트 안의 경로** — SSH 들어가서 확인 (`ssh ubuntu@<lightsail-ip>`).

## 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| `install.sh` 가 `R2_ACCOUNT_ID 누락` 으로 종료 | `.env` 에 4개 변수 모두 채웠는지 확인 |
| `rclone lsd r2:...` 실패 | 토큰 권한 (`Object Read & Write`) 또는 버킷 범위 (`household-backup` 한정) 잘못. R2 대시보드에서 토큰 재발급 |
| `docker compose exec postgres pg_dump` 가 멈춤 | postgres 컨테이너 안 떠있음 — `docker compose ps` 확인 |
| 다음 날 백업 로그 없음 | `crontab -l` 로 `# household-backup` 라인 확인. 없으면 `install.sh` 재실행 |
| 배포 이후부터 `Permission denied` (백업 또는 리허설) | 배포의 `git reset --hard` 가 실행비트를 벗김. git 이 스크립트를 100755(exec)로 추적해야 함 — `git update-index --chmod=+x infra/backup/backup-db.sh infra/backup/restore-drill.sh` 후 커밋. 서버 응급조치는 `chmod +x` (단 다음 배포 전까지만 유효). Windows 는 `core.filemode=false` 라 로컬 파일 권한만으론 안 담긴다 |
| 업로드 로그에 `NotImplemented 501` 뒤 `Attempt 2/3 succeeded` | rclone S3 backend 가 R2 미지원 API 를 한 번 찔러보고 재시도 성공하는 노이즈. 백업 자체는 성공(`backup OK` 확인). 무시 가능 |
| 백업 파일명 날짜가 하루 전 / cron 03:00 이 한국 시각 아님 | 호스트 timezone 이 UTC. `sudo timedatectl set-timezone Asia/Seoul` 또는 `install.sh` 재실행 |
| R2 비용 알림 메일 옴 | 즉시 `rclone size r2:household-backup` 로 사용량 확인. 30일 retention 안 도는지 점검 |
| `drill FAILED: psql 복구 실패` | **백업 자체가 쓸 수 없는 상태** — 로그 tail 20줄 확인 후 `backup-db.sh` 수동 실행해 새로 뜨기. 사고 대응 가능한 마지막 백업은 R2 의 그 이전 날짜 파일 |
| `drill FAILED: 한글 0행` | UTF8 인코딩 손상. 임시 DB 생성 시 `ENCODING 'UTF8' TEMPLATE template0` 이 빠졌거나 덤프가 다른 인코딩으로 떠졌음 |
| `drill FAILED: 디스크 부족` | 임시 DB 가 운영과 같은 볼륨을 쓴다. `docker system prune` 또는 수동 복구 때 남은 `household_restore_test` 잔여 DB 정리 (`\l` 로 확인) |
| `drill FAILED: 백업 파일 없음` | `r2:household-backup/daily/` 가 비었음 — 백업 cron 이 안 돌고 있다는 뜻. `crontab -l` 확인 |
| `drill FAILED: 최신 백업이 N시간 전` | 백업이 멈췄다는 신호. `tail /var/log/household-backup.log` + `crontab -l` 확인. 복구 자체는 되는 상태라 조용히 넘어가기 쉬운 고장 |
| 리허설이 로그를 아예 안 남김 | cron 이 스크립트를 실행조차 못 함 — 실행 권한(위 `Permission denied` 행) 또는 `crontab -l` 의 `# household-restore-drill` 라인 확인 |

## 변경 시 주의

- 백업 빈도/시간 변경: `install.sh` 의 `BACKUP_CRON` 의 `0 3 * * *` 부분 수정 후 재실행
- 리허설 빈도/시간 변경: `install.sh` 의 `DRILL_CRON` 수정 후 재실행. **백업보다 뒤 시간이어야** 그날 백업을 검증한다
- retention 기간 변경: `backup-db.sh` 의 `RETENTION_DAYS=30` 수정
- 버킷 이름 변경: `.env` 의 `R2_BUCKET` 만 갱신하면 됨 (스크립트 코드 변경 X)
