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
2026-07-01: 프로젝트 리네이밍 — household-back/front → moeum-back/front (UI 브랜드가 이미 "모음"으로 리브랜딩 완료, 인프라 식별자만 불일치. household만 치환하고 -back/-front 접미사 유지해 변경 최소. moeum-api/web 등 역할기반 대안은 기존 경로/GHCR 히스토리 단절 커서 탈락)
2026-07-01: household 엔티티 처리 — 인프라 식별자만 변경, 도메인 엔티티 유지 (households 테이블·household_id·/api/household·X-Household-Id·app/domain/household는 API 계약이자 앱 핵심 엔티티. 엔티티까지 리네임하면 백-프론트-DB 동반 대공사+API 재계약이라 탈락. 인프라 식별자(이미지/컨테이너/네트워크/GHCR/경로/DB명)만 moeum으로)
2026-07-01: DB명 대소문자 — HOUSEHOLD → 소문자 moeum (Postgres 따옴표 없는 식별자 소문자 폴딩 → 대문자 DB명은 항상 따옴표 필요+툴 깨짐. 맥미니 이전 시 dump→restore로 새 이름 생성하므로 지금이 정리 적기)
2026-07-01: 서버 이전 방식 — Lightsail → 맥미니 + Cloudflare Tunnel (맥미니 공인IP 없음 → DNS 프록시 불가. cloudflared 아웃바운드 터널로 웹·SSH 내보내 인바운드 포트 0개. TLS는 CF 엣지 종단 → origin nginx SSL/AOP 제거. GHCR·compose·ssh-action 파이프라인은 재활용. 웹 moeum.jinho826.com/SSH ssh.jinho826.com)
2026-07-01: CI SSH 터널 통과 — cloudflared access tcp 포트포워딩 + service token (appleboy/ssh-action이 Go crypto/ssh라 명세서의 proxy_command 미지원. 러너에서 cloudflared access tcp로 localhost:2222 포워딩 후 appleboy host=localhost 접속. CF Access는 비대화형 service token으로 인증)
