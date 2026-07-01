# moeum 리네이밍 + 맥미니(Cloudflare Tunnel) 서버 이전 — 실행 계획

> 2026-07-01 수립. **아직 미착수** — 나중에 이 문서 보고 사용자와 한 단계씩 같이 진행.
> 원본 plan: `~/.claude/plans/synthetic-yawning-nebula.md` (동일 내용).

## Context / 왜

가계부 앱 UI 브랜드는 이미 "모음"으로 리브랜딩 완료(`household-front` `manifest.json`, i18n `brand_name`/`meta_title`)됐는데, 인프라 식별자(리포/이미지/컨테이너/DB/도메인)는 아직 `household-*`라 불일치. 동시에 서버를 **AWS Lightsail(공인IP+nginx SSL) → 집 맥미니(사설IP)** 로 이전. 맥미니는 공인IP 없음 → DNS 프록시 대신 **Cloudflare Tunnel**(아웃바운드 터널, 인바운드 포트 0개)로 웹·SSH 내보냄.

본질 변경 한 줄: `도메인→CF DNS→Lightsail 공인IP→nginx` **→** `도메인→CF→cloudflared 터널→맥미니 localhost`. GHCR·docker compose·ssh 배포 파이프라인은 재활용.

**이 작업은 맥미니에서 직접 명령 치는 수동 작업이 많아 사용자와 한 단계씩(Phase 단위) 같이 진행한다.**

## 확정 결정 (사용자, 2026-07-01)
| 항목 | 선택 |
|---|---|
| 이름 | `household-back`→`moeum-back`, `household-front`→`moeum-front` (household만 치환, `-back`/`-front` 유지) |
| 엔티티 | **인프라 식별자만 변경. 도메인 엔티티 `household`(가계부) 유지** |
| DB | 이전 시 dump→restore 하며 DB명도 moeum으로 (**소문자 `moeum` 권장** — 대문자는 psql 따옴표 지옥) |
| 도메인 | 웹 `moeum.jinho826.com`, SSH `ssh.jinho826.com` |

## 절대 안 건드리는 것 (도메인 = 가계부)
`households`/`household_members` 테이블, 모든 `household_id` 컬럼/인덱스, `/api/household*` 라우트, `app/domain/household/*`, `X-Household-Id` 헤더, `ddl/init.sql`, 문서의 도메인 설명 표. **API 계약이라 건드리면 프론트·DB 동반 붕괴.**

---

## 1. 리네이밍 — 무엇 → 무엇

### 1-A. 크로스 리포 결합 (한쪽만 바꾸면 502 — 한 세트로 커밋)
| 항목 | 현재 → 변경 | 참조 파일 |
|---|---|---|
| 공유 external 네트워크 | `household-net`→`moeum-net` | back `docker-compose.yml:47,65`, front `docker-compose.yml:15,61` |
| 백엔드 컨테이너명 | `household-back`→`moeum-back` | back `.env`(DOCKER_CONTAINER_NAME); **front 참조**: front `docker-compose.yml:10`(BACKEND_URL), front `nginx/nginx.conf:62`(upstream backend) |

### 1-B. 백엔드 (`household-back` 리포)
- `.env.example`/서버 `.env`: `DOCKER_IMAGE_NAME`·`DOCKER_CONTAINER_NAME`→`moeum-back`(6,7), `APP_NAME`→`moeum`(4), `POSTGRES_USER`→`moeum`(13), `POSTGRES_DB HOUSEHOLD`→**`moeum`소문자**(15), `DATABASE_URL` 유저·DB명 소문자 moeum(17), 예시 도메인→`moeum.jinho826.com`(32)
- `docker-compose.yml`: `container_name household-postgres`→`moeum-postgres`(5), 네트워크 `household-net`→`moeum-net`(39,47,65)
- `app/core/config.py:14` `APP_NAME`→`"moeum"`, `pyproject.toml:2` `name`→`"moeum"`(런타임 무관, uv.lock 재생성)
- `infra/backup/backup-db.sh:23`(파일 prefix `household-`→`moeum-`), `install.sh:13`(로그명 `household-backup.log`→`moeum-`), `install.sh:76,77`(cron 마커 `# household-backup`→`# moeum-backup`)
- `.github/workflows/deploy.yml`+`rollback.yml`: `IMAGE_NAME`/`GHCR_REPOSITORY`→`moeum-back`(9,10), 서버경로 `~/household/household-back`→`~/moeum/moeum-back`(62,81 / rollback 53,71-74), stuck 컨테이너 필터명(90,91), rollback GHCR API 경로 `.../container/moeum-back/versions`(27)
- `.claude/settings.json:2`, `README.md:1`, `CLAUDE.md:1`, `docs/api-list.md:1`(문서/로컬, 선택)
- **수정 불필요**: `Dockerfile`, `entrypoint.sh`, `ddl/init.sql`

### 1-C. 프론트 (`household-front` 리포)
- `package.json:2` `name`→`moeum-front`
- `docker-compose.yml`: 기본값(4,5)→`moeum-front`, `BACKEND_URL`(10)→`http://moeum-back:8000`, 네트워크(15,61)→`moeum-net`, `container_name`(37)`household-front-nginx`→`moeum-front-nginx`
- `.env:4,5` 이미지/컨테이너명→`moeum-front`
- `nginx/nginx.conf:62` upstream backend→`moeum-back:8000`, 도메인(82,88,89,96)→`moeum.jinho826.com` (단 §3에서 전면 재작성)
- `.github/workflows/deploy.yml`+`rollback.yml`: IMAGE_NAME/GHCR/서버경로(9,10,65 / rollback 11,12,27,52)→`moeum-front`
- **수정 불필요**: `next.config`(BACKEND_URL 환경변수만 읽음), 브라우저 상대경로 `/api`(apiBaseUrl=""), `NEXT_PUBLIC_BACKEND_URL` 공란 유지

### 1-D. DB명 소문자 권장
현재 `HOUSEHOLD`(대문자). Postgres는 따옴표 없는 식별자를 소문자 폴딩 → 대문자 DB명은 항상 `"HOUSEHOLD"` 따옴표 필요, 일부 툴 깨짐. 이전 시 어차피 새 이름 restore → 지금이 정리 적기. `.env`의 `POSTGRES_DB`와 `DATABASE_URL`(17) **둘 다** 소문자 `moeum`.

---

## 2. GHCR 리포명 변경 영향
- `ghcr.io/yangjinho826/moeum-back` 첫 push 시 **새 패키지 생성**. 기존 `household-back` 패키지·태그 히스토리는 자동삭제 안 됨(보존, 새 이름과 분리).
- **이전 직후 rollback.yml 실패 정상**: 새 패키지 태그 1개뿐 → `sort -ru | sed -n '2p'`(직전 태그) 없음. 2회차 배포 후 정상화. 이전 직후엔 롤백 대신 재배포로 대응.
- rollback.yml GHCR API 경로 반드시 수정(back/front 각각 `moeum-back`/`moeum-front`).
- 검증 완료 후 옛 `household-*` 패키지 수동 삭제(옵션).

---

## 3. Cloudflare Tunnel — nginx 재설계 (프론트 `nginx/nginx.conf`)

터널이 TLS를 **CF 엣지가 종단**하고 로컬로 평문 전달 → origin nginx의 TLS 장치 전부 불필요.

| 요소 | 처리 | 이유 |
|---|---|---|
| SSL termination(`ssl_certificate`, 443 listen) | **제거** | CF 엣지가 TLS 종단, origin 평문 80 |
| Authenticated Origin Pulls(`ssl_verify_client on`, `cloudflare-origin.pem`) | **제거** | 공인 origin 없음. 터널 자체가 인증 채널 |
| 80→443 리다이렉트 / 443 `default_server` | **제거** | 평문 80 단일 진입. HTTP→HTTPS는 CF "Always Use HTTPS" |
| `./nginx/ssl` 마운트 + `443:443`(front compose) | **제거** | 인증서·인바운드 포트 불필요 |
| `/api`→backend, `/`→frontend 라우팅 + `proxy_redirect` | **유지** | 경로분기·SSR Location rewrite 핵심 |
| `real_ip` | **축소 유지** | `set_real_ip_from 127.0.0.1`만, CF IP 대역 목록 제거, `real_ip_header CF-Connecting-IP` 유지 |

**터널 대상 = nginx 유지(권장).** Public hostname `moeum.jinho826.com` → `http://moeum-front-nginx:80`(도커망 상 cloudflared 컨테이너) 또는 `localhost:80`(compose `127.0.0.1:80:80`). nginx가 경로분기·SSR rewrite 담당 → 프론트 직결보다 견고. (프론트 직결 시 cloudflared ingress path 분기 제한 + SSR Location rewrite 소실 → 비권장)

재작성 골자:
```
upstream frontend { server frontend:3000; }
upstream backend  { server moeum-back:8000; }
server {
  listen 80;
  server_name moeum.jinho826.com;
  set_real_ip_from 127.0.0.1;
  real_ip_header CF-Connecting-IP;
  client_max_body_size 10M;
  location /api/ { proxy_pass http://backend; ...기존 헤더... }
  location /    { proxy_pass http://frontend; ...기존 rewrite/헤더... }
}
```

---

## 4. DB 데이터 이전 (Lightsail → 맥미니, HOUSEHOLD→moeum)

**함정**: `ddl/init.sql`은 pgdata 볼륨이 빌 때만(initdb) 실행 → 맥미니 새 볼륨에서 스키마 생성 후 restore가 같은 테이블 재생성하려다 충돌.

절차:
1. Lightsail app stop(쓰기 정지) → `docker compose exec -T postgres pg_dump -U household -d HOUSEHOLD --no-owner --no-privileges | gzip > moeum-migrate.sql.gz`
2. 맥미니로 전송(scp 터널 경유 또는 R2 rclone `r2:household-backup/pre-deploy/<latest>`)
3. 맥미니 `.env` `POSTGRES_DB=moeum`·`POSTGRES_USER=moeum` → **ddl 마운트 임시 비활성**(또는 restore 전 `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`)하고 postgres up → 빈 `moeum` DB
4. `gunzip -c moeum-migrate.sql.gz | docker compose exec -T postgres psql -U moeum -d moeum` (`--no-owner`라 롤명 무관, dump에 `alembic_version` 포함)
5. app up → `entrypoint.sh`의 `alembic upgrade head`는 이미 head라 no-op
6. ddl 마운트 원복

---

## 5. CI/CD 워크플로우 (Lightsail SSH → 맥미니 터널 SSH)

**주의(명세서와 다름)**: `appleboy/ssh-action`은 Go crypto/ssh라 임의 `proxy_command`(명세서 방식) 미지원. 대체:
1. 러너에 cloudflared 설치 step
2. `cloudflared access tcp --hostname ssh.jinho826.com --url localhost:2222` 백그라운드. CF Access 인증은 **service token**(비대화형) — env `CF_ACCESS_CLIENT_ID`/`CF_ACCESS_CLIENT_SECRET`
3. appleboy `host: localhost, port: 2222`
(또는 appleboy 버리고 러너에서 raw `ssh -o ProxyCommand='cloudflared access ssh --hostname %h'`)

시크릿 정리:
- 제거: `LIGHTSAIL_HOST`/`USER`/`SSH_KEY`
- 추가: `MACMINI_SSH_USER`, `MACMINI_SSH_KEY`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`

그 외: IMAGE_NAME/GHCR→`moeum-*`, 서버경로 `~/moeum/*`, stuck 필터명, rollback API 경로, pre-deploy dump step `POSTGRES_DB=moeum`(.env 자동).

---

## 6. 실행 순서 (무중단 불필요 → 최단·최안전)

**원칙**: 리네이밍을 코드에 먼저 반영, Lightsail은 DNS 컷오버까지 살려둠(롤백 = DNS 되돌리기). 맥미니 수동 셋업은 리포 커밋과 분리.

### Phase A — 맥미니 수동 셋업 (사용자가 맥미니에서 실행, Claude와 확인)
- [ ] 전용 유저 + sshd 활성화(공개키만, `PasswordAuthentication no`)
- [ ] 절전 방지 `sudo pmset -a sleep 0 disablesleep 1`
- [ ] Docker(Desktop/colima) 설치, `docker login ghcr.io`(read:packages PAT)
- [ ] cloudflared 설치 → `tunnel login` → `tunnel create moeum`
- [ ] CF Access: `ssh.jinho826.com` application + service token 발급(ID/Secret 보관)
- [ ] Tunnel ingress: `moeum.jinho826.com`→`http://moeum-front-nginx:80`, `ssh.jinho826.com`→`ssh://localhost:22`
- [ ] `docker network create moeum-net` (external이라 자동생성 안 됨)
- [ ] 리포 clone `~/moeum/moeum-back`·`~/moeum/moeum-front` + 서버 `.env`(moeum 값)

### Phase B — 리네이밍 코드 변경 (두 리포, 각 브랜치 → 함께 머지)
- [ ] 백엔드 §1-B 전부
- [ ] 프론트 §1-C 전부
- [ ] 프론트 nginx §3 재작성 + compose 443/ssl 마운트 제거
- [ ] 워크플로우 §5 (cloudflared tcp-forward + service token, 시크릿 갱신)

### Phase C — 이미지 빌드/푸시
- [ ] `v*` 태그/`workflow_dispatch`로 moeum-back·moeum-front 새 GHCR push (배포 전)

### Phase D — DB 이전 (§4)
- [ ] Lightsail 최종 dump → 맥미니 restore(빈 `moeum`) → alembic no-op 확인

### Phase E — 컷오버
- [ ] 맥미니 backend+front(nginx) up, `moeum-net` 연결 확인
- [ ] cloudflared 기동, 터널 Healthy(초록)
- [ ] CF DNS `moeum.jinho826.com`→터널 CNAME(proxied), "Always Use HTTPS" on
- [ ] 브라우저 검증(`/`, `/api/*`, 로그인, X-Household-Id 흐름)
- [ ] GH secrets 갱신 → `workflow_dispatch` 배포 리허설 1회
- [ ] backup 재설치 (**macOS 대응** — install.sh는 Linux 전용: `apt`/`timedatectl` 없음. rclone `brew`, cron→`launchd` 별도)

### Phase F — 정리 (검증 기간 후)
- [ ] Lightsail 인스턴스 + `household.jinho826.com` DNS 폐기
- [ ] 옛 GHCR `household-*` 패키지 삭제(옵션)

---

## 7. 함정 요약
1. external network 동시 변경 + 맥미니 `docker network create moeum-net` 선행
2. 백엔드 컨테이너명 = front 참조 3곳(DOCKER_CONTAINER_NAME, front BACKEND_URL, front nginx upstream) 한 세트
3. DB명 변경 시 `.env` `POSTGRES_DB` + `DATABASE_URL`(17) 둘 다 소문자 moeum
4. R2 버킷 `household-backup` **유지 권장**(새 버킷=토큰+rclone 재설정+과거 dump 이관 부담). prefix/로그/cron 마커는 cosmetic 변경 무해
5. macOS backup: install.sh Linux 전용 → launchd/crontab 별도 검토
6. initdb 재실행 방지(§4 절차), init.sql 절대 수정 금지
7. rollback 첫 배포 공백(2회차 후 정상)
8. cloudflared service token 정책 허용 필수(아니면 CI SSH hang)
9. CF SSL/TLS: 터널은 origin 평문이라 "Always Use HTTPS" 켜서 사용자 HTTP→HTTPS 보장

## 검증
- 리네이밍 후 로컬: 두 리포 `docker compose config`로 네트워크·컨테이너명 정합, `docker compose up` 후 front→`moeum-back` 프록시 200
- 백엔드 `uv run pytest` 통과(리네이밍이 도메인 로직 안 건드림 확인)
- 컷오버 후: `https://moeum.jinho826.com`, `/api/*`, 로그인, `ssh macmini`(ProxyCommand cloudflared), GH Actions deploy job 통과

## Critical Files
- `household-back\docker-compose.yml`, `household-front\docker-compose.yml`
- `household-front\nginx\nginx.conf` (SSL/AOP 제거 + 평문 80 재작성)
- `household-back\.env.example`
- 양쪽 `.github\workflows\deploy.yml` + `rollback.yml`
- 참고(수정 금지): `household-back\ddl\init.sql`, `entrypoint.sh`, `infra\backup\*`
