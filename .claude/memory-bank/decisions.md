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

2026-05-27: 포트폴리오 차별화 컨셉 — **"1인 SRE 운영 트랙"** 채택 (코드 잘 짜는 신입~주니어는 흔함, 본인 사이드를 SaaS처럼 관측성·인시던트 대응까지 운영한 기록이 면접 차별화 무기. plan: `~/.claude/plans/hashed-inventing-sprout.md`)

2026-05-27: 모니터링 스택 — **하이브리드** 채택 (Sentry + Prometheus/Grafana + Loki + Tempo + Uptime Kuma + OpenTelemetry). 대안: SaaS만 / LGTM 풀스택. 하이브리드 선택 이유: Sentry는 셋업 빠른 에러 표준, Prom/Grafana는 SRE 어필 도구, 다 무료 셀프호스팅, Lightsail 메모리 부담은 별도 Oracle Cloud Free ARM 분리로 해결 가능.

2026-05-27: 어플 배포 — **Capacitor wrap** 채택 (PWA → iOS App Store / Google Play). 대안: PWA 심화 / React Native 재작성. Capacitor 선택 이유: PWA manifest 이미 있어서 1~2일 작업, 스토어 진짜 배포로 포폴 임팩트 최대, RN 재작성은 시간 X.

2026-05-27: 운영 어필 깊이 — **Level 3 (RUNBOOK + 인시던트 2건 + 회고)** 채택. 대안: Level 1(도구 도입만) / Level 2(알람만). Level 3 선택 이유: 신입~주니어가 절대 못 하는 영역, 인위 장애 시뮬레이션 + 실제 알람 타임스탬프 + Discord 메시지 + Grafana 마커가 면접 스토리텔링 무기.

