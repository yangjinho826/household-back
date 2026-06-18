# 활성 컨텍스트

## Goal

**household-back 코드베이스 분석 가이드 (입문자용 코드 산책)** (2026-06-18 시작). 17개 도메인 + core 인프라를 **FastAPI 처음 보는 주니어 개발자**가 혼자 읽을 수 있게 도메인별로 쉽게 풀어낸 마크다운 시리즈를 `docs/codewalk/` 에 작성. 코드는 변경 X (순수 분석 문서). 이직 포폴/온보딩 자산. `docs/testing/` 트랙의 자매격.

## Status

**배치1 완료** — `docs/codewalk/`:
- `README.md` (시리즈 목차 + 도메인 의존성 지도 + 진행 현황)
- `00-overview.md` (프로젝트 정체 · 4층 레이어드 · 요청 10단계 생애주기 · FastAPI 4개념 입문 · 공통 규약 · root_path 함정)
- `01-core-infra.md` (get_db 트랜잭션 경계 · BaseEntity · ApiResponse · 예외체계 · JWT/CurrentUser · 멱등성 상태머신 · 스케줄러 5잡 · 페이징)

톤/형식 사용자 검수 대기 중. **계획은 codex(외부모델) 교차리뷰 + 직접 코드검증 거쳐 개정됨** (계획파일: `~/.claude/plans/spicy-herding-zebra.md`).

## Context

- **9개 문서 구조**: 00 overview / 01 core / 02 auth·user·household / 03 account / 04 category·transaction / 05 fixed·snapshot / 06 portfolio-trading / 07 pricing·snapshot·wealth / 08 home·stats·settings.
- **공통 7섹션 템플릿**: ①한마디 ②개념 콕 ③데이터 모델 ④핵심 로직 코드리딩(대표흐름만 깊게) ⑤API 표 ⑥데이터 흐름 ⑦꼭 기억할 규칙.
- **검증된 코드 사실** (codex+직접확인): ORM relationship 0개(논리FK+서비스검증, transaction만 ForeignKey 2개) / market_price·exchange_rate 라우터 미등록(내부·배치 전용) / 스케줄러 5잡(환율·국장·미장·멱등cleanup·월간스냅샷) / is_archived≠soft-delete / CurrentHousehold=X-Household-Id 헤더 / root_path="/api"+prefix=실제URL / alembic/versions 22개.
- **사실 근거 우선순위**: 1차=model.py+alembic/versions, router.py, service.py / 보조(불일치 가능)=ddl/init.sql, docs/api-list.md / 설계의도 참고=decisions.md.
- **진행 방식**: 영역별 배치로 끊어가며. 배치1 후 톤 합의 → 02~08 반영.
- 도메인 규모: portfolio 2216 · transaction 1418 · account 859 · household 701 · fixed 595 · category 521 · account_snapshot 475 · core 1300줄.

## Next Step

1. 사용자 톤 검수 피드백 반영.
2. **배치2** — `02-auth-user-household.md` (회원가입→로그인→토큰갱신 + 세대/멤버 + CurrentHousehold) + `03-account.md` (통장 타입·잔액 공식·is_archived). 영역 코드 Explore 정밀수집 → 입문자 톤 작성 → file:line 교차확인.
3. 배치3~5 순차 (04·05 → 06·07 → 08).
