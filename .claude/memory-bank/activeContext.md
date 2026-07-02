# 활성 컨텍스트

## Goal

**자산 추이 차트 원가박제 해결 — 시세 이력(market_price_history) 시가 박제** (2026-07-02).
투자계좌 손실(KRX금계좌 -4.42% 등)이 "자산 추이" 그래프에 안 뜨고 원가로 평평하게 박제되던 문제. 박제 시 그 달 시가로 평가하도록 전환.

## Status

**백엔드 구현·검증 완료. 미커밋.** (브랜치 `feat/asset-trend-market-price`)

- 신규: `market_price/model.py`(MarketPriceHistory), `repository.py`(upsert/find_prices_for_month), 마이그레이션 `a7c3e9d1f4b8`(테이블 code/market/price_date/price + unique + index)
- `yahoo_client.py`: `fetch_monthly_closes`(interval=1mo 월봉) 추가, HTTP+retry를 `_request_chart`로 공용화
- `market_price/service.py`: `backfill_yahoo_monthly`(야후 월봉→upsert, USD환산), `snapshot_other_prices`(OTHER current_price→그 달), `value_holdings_at_month`(item 현재 code/market 기준 시가평가, 없으면 원가 fallback)
- 박제 로직: `account/service.py:_calc_investment_balance` as_of 분기 + `portfolio/snapshot_service.py` → `value_holdings_at_month` 호출
- 스케줄러: `account_snapshot/service.py` 자동/수동 박제 직전 시세 확보(backfill + OTHER 저장) 연결
- DB 정리: 사라진 이전 세션 마이그(675b4925ec18)이 dev DB `alembic_version`에 남아 체인 깨짐 → version을 c8e1f4a7d2b9로 직접 UPDATE + 기존 테이블 drop 후 재적용

**스모크 검증 (dev DB, KRX금계좌 금 26주):** 시세없음→원가(5,363,592, pl 0) / 시세 15만저장→시가(3,900,000, pl -1,463,592) / 다른달→원가fallback / upsert 멱등. 전부 통과(rollback).

## Context

- **자산 추이 = account_snapshots.balance**(월별 박제). 기존엔 `_calc_investment_balance(as_of)`가 과거 시가 없어 원가로 평가 → 손익 0. 이제 시가.
- **종목별 시세 출처 분기**: 야후 종목(KRX/US)은 월봉 backfill 가능, 금 등 `Market.OTHER`는 야후 미지원이라 박제 시점 current_price를 그 달로 저장(과거 소급 X = "현재부터").
- **실데이터 함정**: 금 종목이 tx엔 market=KRX_KOSPI, item엔 OTHER. `asof_holdings`(tx기반)와 시세이력(item기준 저장)이 어긋남 → `value_holdings_at_month`가 item_id로 현재 code/market 교정해 해결.
- **회귀 안전**: 시세 이력 없으면 원가 fallback → 금 과거·수집실패 종목은 기존과 동일.
- tests/ 인프라 없음(과거 관행상 미커밋) + upsert가 postgres on_conflict 전용이라, pytest 대신 dev DB 스모크로 검증.

## Next Step

1. **실제 박제로 end-to-end 확인** (선택) — dev에서 수동 박제(POST /account-snapshot/create) 돌려 /wealth·/account-snapshot/yearly 응답에 금 손실 반영 확인.
2. **커밋** — feat 브랜치. 마이그+model+repo+service+박제로직 묶음. (tests 미포함 관행)
3. **프론트** — 자산 추이 YAxis(손익 음수 표시) 대응은 프론트 별도 작업.
4. 과거 backfill 1회 실행 여부 결정(야후 종목만, 실 데이터에 금밖에 없으면 불필요).
