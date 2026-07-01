# 활성 컨텍스트

## Goal

**moeum 리네이밍 + 맥미니(Cloudflare Tunnel) 서버 이전** (2026-07-01 수립).
프로젝트 인프라 식별자 `household-*`→`moeum-*` 통일 + AWS Lightsail→집 맥미니 이전(공인IP 없음 → Cloudflare Tunnel).

## Status

**계획 수립 완료, 미착수.** 상세 실행계획 → `.claude/memory-bank/moeum-migration-plan.md` (원본: `~/.claude/plans/synthetic-yawning-nebula.md`).
맥미니에서 직접 명령 치는 수동작업 많음 → **사용자와 Phase 단위로 한 단계씩 같이 진행** 예정.

확정 결정 4건: ①이름 `moeum-back`/`moeum-front`(household만 치환) ②도메인 엔티티 `household`(가계부) 유지, 인프라 식별자만 변경 ③DB명 `HOUSEHOLD`→소문자 `moeum`(dump→restore 시) ④웹 `moeum.jinho826.com`·SSH `ssh.jinho826.com`.

## Context

- **`household` 2종 구분 필수**: (가)인프라 식별자=변경대상 vs (나)도메인 엔티티 "가계부"(`households`테이블·`household_id`·`/api/household`·`X-Household-Id`·`app/domain/household/*`·`ddl/init.sql`)=**절대 유지**. 후자 건드리면 API 계약 붕괴.
- **크로스 리포 결합 3곳 한 세트**: 공유 network `household-net`→`moeum-net`(양쪽 compose), 백엔드 컨테이너명 `household-back`→`moeum-back`(back .env + front `BACKEND_URL` + front `nginx.conf:62 upstream`). 한쪽만 바꾸면 502.
- **프론트 UI는 이미 "모음" 리브랜딩 완료**(manifest/i18n) — 그래서 인프라도 통일하는 것.
- **nginx 재설계**: 터널이 TLS 종단 → 프론트 `nginx/nginx.conf`의 SSL termination·Authenticated Origin Pulls·80→443 리다이렉트 전부 제거, 평문 80만. 경로분기(`/api`↔`/`)·SSR rewrite는 유지. 터널 대상은 nginx 유지 권장.
- **DB 이전 함정**: `ddl/init.sql`(initdb)와 pg_dump restore 충돌 → restore 시 ddl 마운트 임시 비활성 또는 DROP SCHEMA 선행.
- **appleboy/ssh-action은 명세서의 `proxy_command` 미지원** → `cloudflared access tcp` 러너 포트포워딩 + CF service token으로 대체.
- R2 버킷 `household-backup` 유지 권장. macOS backup은 install.sh(Linux 전용) launchd 별도 대응.

## Next Step

1. **Phase A — 맥미니 수동 셋업**(전용유저/sshd/Docker/cloudflared/CF Access/`docker network create moeum-net`/리포 clone). 사용자와 같이.
2. **Phase B — 리네이밍 코드 변경**(두 리포 §1-B/1-C + nginx 재작성 + 워크플로우). 각 브랜치 → 함께 머지.
3. Phase C 이미지 push → D DB이전 → E 컷오버(DNS) → F Lightsail 정리.
   (전체 체크리스트는 moeum-migration-plan.md §6)
