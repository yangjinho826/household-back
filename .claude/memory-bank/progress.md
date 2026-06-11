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
- [x] 2026-06-09: 워크스루 1번(auth·user) 완주 — user 5엔드포인트 + auth(login/refresh/logout). 토큰 2종 비대칭(access stateless / refresh stateful+회전5개) / refresh 검증 3단 / CurrentUser 2단 의존성. 곁다리로 관찰점 ①(CustomException이 Exception 상속이라 Pydantic validator 통과→구체 에러코드 보존) 추적. 관찰점 2개(dead 분기/naive datetime) notes.md 기록.
- [x] 2026-06-10: 워크스루 2번(household) 완주 — CRUD+권한 도메인이라 핵심만 압축. owner_id 진실원(members.role은 표시용) / cascade soft-delete(수동 bulk UPDATE 8자식, AccountSnapshot만 subquery) / CurrentHousehold=JWT+X-Household-Id 헤더 멤버십 합성 의존성(household 라우터 자신은 path param). 헤더 vs path param 구분(현재 컨텍스트 vs 특정 리소스). 난이도 실측 → 알맹이는 3·4·6에 몰림 확인, 이후 알맹이 직격 모드 전환. 관찰점 1개(JOIN) notes.md.
- [x] 2026-06-11: 워크스루 3번(account) 완주 — 사용자 요청으로 알맹이 직격 대신 **9단계 정독**. 핵심 ①**잔액 컬럼 없음** — balance = start_balance + Σ거래를 매 조회 재계산(거래의 함수 → 동기화 버그 구조적 차단). ②`_cash_flow` 순수공식(income+ expense- transfer_out- transfer_in+ valuation_net+), 수동자산(부동산/연금/금)도 VALUATION 거래로 표현해 같은 공식 흡수 → 분기 안 만듦(케이스를 통일). ③INVESTMENT만 분기(`_calc_investment_balance`) = 잔여현금(현금흐름−매수+매도) + 보유종목 평가액(Σ수량×현재가), 평가손익 실시간 반영. ④`sum_for_account` 집계는 group by 4컬럼(tx_type/account_id/to_account_id/valuation_direction), 이체는 `or_`로 양방향 잡고 if 2개로 분배(자기이체 상쇄). ⑤**단건/배치 이중구현**(`_calc_*` 쿼리내장 vs `_build_*`+`_load_balance_sources` 3쿼리 선로드) — list N+1 막는 의도적 DRY 빚. ⑥리포트=박제 스냅샷(과거월)+실시간 집계(이번달) 합성. ⑦삭제 cascade=solo먼저+이체는 상대 죽은 것만(D안, 본체 죽이기 전에 처리해야 자기오판 방지). **교훈: 빡센 게 알고리즘이 아니라 도메인 설계 결정(케이스를 안 만들게 추상화 지점=거래를 잘 잡음)**.

## 진행 중
- [ ] 소스분석 학습 트랙 — account 완주(9단계). 다음 **transaction**(원장 running balance + `_signed_amount`) → portfolio. 채팅 워크스루.

## 막힘
- [x] 2026-06-04: 평가금 수정 거래화면 이동(통장 칩+타입분기) + 모바일 삭제버튼 z-index 수정 + 도커 DB 포트 override
