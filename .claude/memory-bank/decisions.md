# 결정 기록

> `/decide` 호출 시 결정 결과가 여기에 자동 append.
> 형식: `YYYY-MM-DD: <주제> — <선택 옵션> (<근거>)`

---

2026-06-03: 통장 삭제 시 이체 처리 — D안(이체 행 유지) (상대 통장이 살아있으면 이체 행을 보존해 상대 잔액·통계 무결성 유지. A안(이체→단순거래 변환)은 통계왜곡+비가역이라 탈락. 거래조회 양방향 `or_(account_id, to_account_id)` + transfer_in/out 분리집계라 코드상 자연스럽게 동작)
2026-06-03: 통장 삭제 정책 — 보유종목만 차단 + 나머지 cascade soft-delete (단독거래/수동자산/종목이력/스냅샷은 함께 삭제. 투자 데이터(보유종목)만 보호 위해 차단 유지)
2026-06-03: 카테고리 삭제 — 차단 제거하고 soft-delete만 (category_id 유지. `find_by_ids`가 data_stat 필터 없어 기존 거래는 이름 조회 O, `find_active_by_household_id`로 새 입력 선택목록엔 제외. 코드 변경 거의 없이 충족)
2026-06-04: 수동자산 모델 — 통장(account) 일원화 + 평가조정(VALUATION) 거래 (ManualAsset+전용계좌 이원화의 '평가액+이체' 단순합산이 평가액 재입력 시 이체분 이중계상. 모든 자산을 account로 통일, 가치변동은 VALUATION 거래로. 잔액=start_balance+거래합. 대안 '성격별 분리'·'이체를 평가액에 흡수'는 복잡도/모호성으로 탈락)
2026-06-04: 평가조정 부호 표현 — valuation_direction 컬럼(INCREASE/DECREASE) (amount는 양수 유지. signed amount는 amount>0 불변량 깨고, UP/DOWN 2타입은 '평가조정' 개념 분할. 방향 플래그가 이체 패턴과 일관)
2026-06-04: 평가액 입력 UX — 현재 총액 절대값 입력 → 차액 자동 VALUATION (사용자는 '지금 얼마'만 입력, 시스템이 (새값-현재잔액) 차액을 평가조정 거래로 생성. 이체는 기존 그대로 별도)
2026-07-21: 포폴 포지션 — "저비용 단일 서버 운영 감각" 보조 카드 (codex 2회 교차검증. 메인4=배포안전망·멱등성·백업복구·알림관측 + 보조2=advisory lock·AI추적. 실사용 미미라 "운영 성과" 아닌 "운영 준비도" 톤. exactly-once/무장애 표현 금지, crash window 는 면접 미끼로 비움)
2026-07-21: 포폴 실측 로드맵 — 1 테스트+CI(실 PG) → 2 주간 복구 리허설(RTO) → 3 장애 알림 → 4 migration playbook (k6 절대처리량 폐기 — 1vCPU 숫자 무의미. 동시 중복 검증은 k6/멀티스레드 아닌 pytest asyncio.gather + compose 인스턴스 2개 실증. 상세 docs/portfolio-sre-roadmap.md)
2026-07-24: 테스트 스키마 생성 — alembic upgrade head (session 1회) (metadata.create_all 은 모델기준 → 마이그레이션 22개와 drift 시 테스트통과·운영깨짐. alembic 경로가 CI서 검증되는 부가효과. 이후 TRUNCATE 격리)
2026-07-24: 테스트 격리 — 매 테스트 TRUNCATE CASCADE (tx-rollback 아님. 멱등성 동시성 테스트는 요청마다 독립 커넥션 필요 → 단일커넥션 롤백 fixture 는 경합 무효화. alembic_version 제외)
2026-07-24: 동시성 테스트 신뢰성 — negative control 역증명 필수 ("결과 1건"만으론 순차 실행과 구분불가 = 올바른 멱등성은 순차도 1건. 락 우회 버전이 동일 하니스로 N건 만드는 걸 보여야 경합이 진짜임 증명. 포폴·면접 카드로도 강력)
2026-07-24: CI 게이트 위치 — ci.yml(push/PR) + deploy.yml(needs:test) 둘 다 (deploy 는 tag push 트리거뿐 → 그것만 걸면 평소 "깨진 채 머지". 백업 게이트와 2중)
2026-07-24: 도메인 통합테스트(D) 범위 — 🔴 핵심 4~5개만 (transaction 잔액/portfolio realized_pnl/household IDOR/auth. 전수 17개는 ROI 낮고 포폴 초점 흐림. 돈·권한 경로만 두껍게)
2026-07-27: 포트폴리오 실현손익 진실 원천 — replay 단일화 ✅ (buy/sell 의 incremental 계산 제거 → `_recalc_item_from_transactions` 로 통일. 대안 "백데이팅 차단"은 과거 거래를 뒤늦게 입력하는 정상 사용을 막는 제품 제약이라 탈락, "자백으로 남김"은 수정 비용이 재계산 호출 한 줄이라 C(crash window, outbox급 필요)와 달리 "알고도 안 고쳤다"가 성립 안 해 탈락. `_recompute_realized_pnl` docstring 이 이미 replay 를 정본으로 선언 = 계약 준수 방향)
2026-07-27: D 도메인 테스트 대상 재확정 — D3(IDOR) 강등, D2 최우선 (착수 전 `app/domain/*/service.py` public 함수 전수 스캔 결과 `find_by_id` 후 소속 검증 누락 0건 → D3 는 GREEN 이 뻔해 회귀 안전망 가치만. user 도메인 예외는 멤버 초대용 설계 선택. 대신 D2 는 코드 독해 단계에서 진실 원천 2개를 발견 → 실측으로 결함 확정)
2026-07-24: 테스트 스키마 생성 정정 — alembic upgrade head ❌ → Base.metadata.create_all ✅ (⓪ 착수해보니 이 레포 alembic baseline 이 빈 마이그레이션 = 운영은 init.sql + `stamp head`. upgrade head 로는 스키마 0개 생성됨. init.sql 도 코드 불일치(idempotency_records 누락)라 소스로 못 씀 → SQLAlchemy 모델이 유일 완전 진실. drift 위험은 별도 인지하되 스키마가 아예 안 생기는 것보다 우선. 앞 결정(2026-07-24 alembic upgrade head) 뒤집음)
