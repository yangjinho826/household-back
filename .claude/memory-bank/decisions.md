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
