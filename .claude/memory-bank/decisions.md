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
2026-07-02: 자산 추이 원가박제 해결 — market_price_history 시세이력 + 종목별 출처 분기 (A안 정공법. 박제 시 원가 대신 그 달 시가로 평가 → 손실이 자산추이에 반영. 야후 종목(KRX/US)은 월봉 `interval=1mo`로 미래수집+과거backfill, 금 등 OTHER는 박제시점 current_price를 그 달로 저장('현재부터', 과거 소급X). 시가 없으면 원가 fallback이라 회귀 없음. B안(current_price 직박제)은 catch-up 왜곡으로 탈락)
2026-07-02: 박제 시가조회 키 — tx기반(asof_holdings) 아니라 item 현재 (code,market) (실데이터에서 종목 market 변경 이력 발견: tx=KRX_KOSPI인데 item=OTHER로 바뀐 금 종목. asof_holdings는 tx.code/market이라 시세이력(item 기준 저장)과 어긋나 원가 fallback로 샘. value_holdings_at_month가 item_id로 현재 code/market 교정해 정합)
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
2026-07-30: 포폴 카드 최종 확정 — 멱등성 / 테스트+CI / 배포 안전망 / 복구되는 백업 4장 + 보조 2장 (백필 카드는 투자 도메인 설명 비용으로 제거·면접 재료로만 보존. 2026-07-21 "메인4=배포·멱등성·백업·알림관측" 구성을 대체 — 알림관측은 로드맵 3번 구현 후 재추가. 정본: carrer/portfolio/household-back.md)
2026-07-31: 장애 알림 채널 — Discord webhook (기존 운영 채널이라 설정 비용 0, curl 한 줄, 외부 모니터링 서비스 Discord 연동 전부 free. Telegram은 기존 이력 없어 이득 없음, ntfy.sh는 무료 topic 보안 약점으로 탈락)
2026-07-31: 헬스체크·cron 감시 — Healthchecks.io + UptimeRobot free 조합 (잡는 실패 유형이 상호배타: dead man's switch=cron 생존, /health 폴링=서버 생존. Uptime Kuma는 동일 서버 자기모순, GH Actions schedule은 지연 5~60분+60일 비활성 자동꺼짐으로 탈락. 서버 발신 알림은 서버가 죽으면 못 나가므로 감시 주체를 서버 밖에 두는 게 원칙)
2026-07-31: cron 자가복구 — 등록부를 register-cron.sh로 분리해 deploy.yml SSH step에서 매 배포 재등록 (멱등·sudo 불필요. HC 감지와 보완: 예방=배포 시 자가복구, 감지=배포 없는 기간 유실을 HC가 잡음. install.sh 통째 실행은 sudo 필요 스텝 때문에 배포에 안 섞음)
2026-08-17: MVP 추가개발 진행 방식 — 6+1 항목을 4단계로 쪼개 하나씩 (사용자 "한번에 다 하지말고 나랑 얘기하면서". 순서 = ①고정지출라벨+거래복사(마이그레이션 0) → ②수수료 → ③매매손익 카드+매도수정 → ④USD. ②→③ 은 카드가 fee 를 표시해 순서 의존. 백엔드만 TDD(RED→GREEN), 프론트는 육안 검증)
2026-08-17: 거래 응답의 고정지출명 — `FixedRepository.find_by_ids` 를 상태 필터 없이 (고정지출 삭제는 soft delete 라 FK SET NULL 이 안 터지고 거래는 fixed_expense_id 를 계속 보유 → ACTIVE 로 거르면 보관/삭제된 항목의 과거 거래가 `고정지출 · —` 로 깨짐. 2026-06-03 카테고리 결정의 선례를 그대로 계승. 프론트가 formOptions.fixedExpenses 로 매핑하는 대안은 그 목록이 is_archived=False 만 내려줘 탈락)
2026-08-17: 매매 수수료 반영 범위 — 평단 가산 + 실현손익 차감 + 매매현금 반영 (증권사 계산과 동일. "실현손익만 차감"·"표시만"은 화면 숫자가 증권사 앱과 갈려 탈락. 기존 거래는 fee=0 이라 replay 결과 불변 = 회귀 없음)
2026-08-17: USD 거래 저장 — KRW 컬럼을 진실 원천으로 두고 거래통화 컬럼 병행 추가 (거래통화로 전환하는 대안은 account/service.py:305-306·wealth/service.py:165·portfolio/repository.py:136 이 quantity*current_price 를 통화 구분 없이 합산해 순자산이 조용히 틀림. 표시·손익률만 거래통화 기준(토스증권식 $ 주 + ₩ 보조). 거래시점 환율은 tx 에 박제하되 currency_rates 가 최신값 1행뿐이라 과거 소급 입력은 최신 환율로 박제되는 한계 인지)
2026-08-17: 스냅샷 보유 집계 — GROUP BY 단순평균 ❌ → 시간순 replay 이동평균 ✅ (`asof_holdings_by_account`. 매도 후 재매수한 종목의 박제 평단이 화면 평단과 갈렸다: 매수10@100→매도5→매수5@200 이면 화면 150 / 집계 133.33. "그대로 두고 기록"·"앞으로 찍는 것만 replay" 대안은 전자가 자산 추이 그래프를 계속 틀린 채 두고 후자는 한 그래프에 두 기준이 섞여 탈락. **소급 변경 리스크가 없다는 게 결정적 근거** — 데모 스냅샷은 시드가 `_build_and_save_snapshot`(화면과 같은 서비스 경로)로 매번 재생성하므로 재시딩만으로 새 기준이 적용된다. 2026-07-27 "실현손익 진실 원천 = replay 단일화"의 연장이자 그 두 번째 경로)
2026-08-17: 거래통화 응답 필드 직렬화 — 프론트 `Number()` 캐스팅 ❌ → 스키마에 직렬화 타입 부여 ✅ (pydantic 은 Decimal 에 PlainSerializer 가 없으면 JSON **문자열**로 내린다. `"230.3823"` 이 `rate.toFixed()` 에서 TypeError 를 내 USD 종목 상세가 통째로 죽었다. Stage 4 QA 때 `$230.3823` 로 같은 뿌리를 보고 프론트에서 덮었던 게 원인을 남겨둔 것 — `core/types.py` 에 `Price`(4자리) 추가하고 `*_ccy`/`fx_rate` 에 `Price`/`Money`/`Rate` 부여, 프론트 방어 제거, 회귀 테스트로 고정)
2026-08-17: 거래 수정의 입력 단위 — 요청 필드 추가 ❌ → tx 의 `price_ccy` 유무로 판정 ✅ (매수·매도는 달러 입력인데 수정만 원화로 받아, 화면의 $240.50 을 되돌려보내면 원화 평단이 환율만큼 찌그러졌다. 프론트도 같은 필드로 입력 단위를 정하므로 양쪽 판정이 구조적으로 어긋날 수 없다. 환율은 재조회 없이 거래에 박제된 `fx_rate` 사용 — 단가 오타 하나 고쳤다고 과거 거래가 오늘 환율로 재평가되면 안 된다)
2026-08-17: 이중통화 표시 게이트 — 값별 판정 ❌ → 종목 단위 단일 판정 ✅ (`isDualCurrencyItem`. 평단은 avgPriceCcy, 현재가는 currentPriceCcy 로 각각 판정하면 레거시가 섞인 해외 종목에서 한 카드에 원화 평단 + 달러 현재가가 나온다. 백엔드가 `profit_loss_ccy` 를 내는 조건(둘 다 존재)과 같은 기준으로 맞춤. 거래통화 손익은 자산 추이 그래프(KRW 기준)와 갈리므로 `"USD 기준"` 라벨 필수. 매매손익 **요약**은 통화가 섞여 더할 수 없으므로 KRW 단독을 스키마 docstring 으로 못박음)
