# 진행 상태

## 완료
- [ ] 초기 셋업
- [x] 2026-05-27: 코드베이스 탐색 (백엔드 11도메인 / 프론트 Next.js 14 + PWA manifest)
- [x] 2026-05-27: 포트폴리오 차별화 컨셉 + 스택 결정 (모니터링 / 어플 / 운영 깊이) — SRE 운영 트랙
- [x] 2026-05-27: 7 Phase 로드맵 plan 파일 작성 → `~/.claude/plans/hashed-inventing-sprout.md`
- [x] 2026-06-03: 통장/카테고리 삭제 정책 개편 (통장 cascade soft-delete D안 + 카테고리 차단 제거) + 프론트 무알림 6곳 fix + stats 회귀 fix
- [x] 2026-06-03: codex 백엔드 전체 QA 7개 수정 (PATCH 이체 깨짐 / fixed_expense_id 검증 / 카테고리 kind / 종목 재계산 스킵 / 수동자산 cascade / 계좌 N+1 배치화 / bcrypt async) + 테스트 13개
- [x] 2026-06-07: 노션 API 레퍼런스 재정리 — 코드 직접 분석(7 에이전트 병렬+공통인프라 직접)으로 개요/인덱스 재작성 + 0~7 도메인 하위페이지 8개 생성 (소스분석 학습 트랙 시작, branch `docs/codebase-study`)
- [x] 2026-06-08: 워크스루 0번(공통 인프라 core) 완주 — 9단계 채팅 워크스루(BaseEntity·soft delete / 응답봉투 / 인증 / 스코프 / 에러 / 페이징 / 멱등성 / 스케줄러 / 부팅). 멱등성 집중 심화(process_acquire 상태머신·ON CONFLICT atomic 락·fingerprint·AcquireResult). `idempotency/service.py` AcquireResult 필드 주석 추가.

## 진행 중
- [ ] 소스분석 학습 트랙 — 노션 0→7 순서로 household-back 소스 따라가기 (다음: 워크스루 1번 auth·user). 채팅 워크스루.

## 막힘
- [x] 2026-06-04: 평가금 수정 거래화면 이동(통장 칩+타입분기) + 모바일 삭제버튼 z-index 수정 + 도커 DB 포트 override
