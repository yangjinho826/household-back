# 자유 메모

## 외부 시스템 참조

### 노션 — 가계부 백엔드 API 레퍼런스 (소스분석 학습 지도)
- 개요/인덱스: https://app.notion.com/p/374a6161032981029d29d7288152fd29
- 0. 공통 인프라 (core): https://app.notion.com/p/378a6161032981b6877fe4b36c209918
- 1. auth · user: https://app.notion.com/p/378a61610329819fb645d9f4d4c7deee
- 2. household: https://app.notion.com/p/378a61610329815b9b1ae10fe550b922
- 3. account · category: https://app.notion.com/p/378a616103298148bfa9d4b0ab9f1ed6
- 4. transaction: https://app.notion.com/p/378a61610329814982cec4633a21a924
- 5. fixed · account-snapshot: https://app.notion.com/p/378a6161032981d0ad47d3d5c4e90649
- 6. portfolio · market-price · exchange-rate: https://app.notion.com/p/378a61610329810daaa7e6bf3e71b450
- 7. stats · home · wealth · settings · enum · health: https://app.notion.com/p/378a6161032981759c11fe4760367e49

## 발견한 잠재 버그 (소스분석 중, 2026-06-07) — 기록만, 수정은 별도 결정

1. **`app/domain/transaction/service.py` `_ledger_start_balance`** — `account: Account` 타입힌트를 쓰는데 `Account` 모델 import 없음 + `from __future__ import annotations`도 없음 → 함수 정의 시점 annotation 평가에서 `NameError` 가능성. (import된 건 `AccountRepository`/`MANUAL_ASSET_ACCOUNT_TYPES`뿐). 실제 모듈 로드/호출 경로 확인 필요.
2. **transaction update 경로 검증 약함** — `PUT /transaction/update/{id}`가 create의 `model_validator`만큼 type별 일관성 검증을 안 함. 특히 VALUATION→다른 타입 전환 시 `valuation_direction` 잔존 정리 로직 없음(`_normalize_to_account`는 to_account만 처리).

### 소스분석 1번(auth·user) 관찰점 (2026-06-09) — 기록만, 수정은 별도 결정

3. **`app/core/auth/deps.py` `get_current_active_user`의 ACTIVE 재확인은 dead 분기** — `data_stat_cd != ACTIVE → FORBIDDEN(403)`인데 도달 불가. `get_current_user`가 부르는 `UserRepository.find_by_id`가 이미 `where data_stat_cd == ACTIVE`라(user/repository.py:16) 비활성 유저는 그 전에 `None → UNAUTHORIZED(401)`로 걸림. → FORBIDDEN 한 겹 죽은 방어.
4. **`app/domain/auth/service.py` naive `datetime.now()`** (line 49·59·118, expires_at/revoked_at). 컬럼은 `DateTime(timezone=True)` tz-aware(model.py:21). 반면 `jwt.py:20`은 `datetime.now(timezone.utc)`로 제대로 함 → **같은 도메인 내 tz-aware/naive 혼재**. 0번의 `core/model.py` naive datetime 이슈와 같은 계열.

### 소스분석 2번(household) 관찰점 (2026-06-10) — 기록만, 수정은 별도 결정

5. **`app/domain/household/repository.py` `find_active_by_user_id`가 JOIN 사용** — 전역 패턴 ①(relationship/JOIN 안 쓰고 `find_by_ids` batch)을 어긴 유일 케이스 중 하나. `select(Household).join(HouseholdMember, ...)`로 한 방 조회. 단 "내가 멤버인 가계부"는 N:M 조회라 JOIN 1쿼리가 batch 2쿼리(member select→household find_by_ids)보다 나음(어차피 단일 쿼리라 N+1 위험 없음). 바로 아래 `list_household_members`는 정직하게 batch(`UserRepository.find_by_ids`) 사용 → **일관성은 깨졌지만 성능은 더 맞는** 케이스. "패턴 어겼는데 사실 더 나은" 예시. 수정 불필요(오히려 JOIN이 정답), 일관성 관점 기록만.

## 학습 노트
(이 프로젝트에서 배운 패턴/팁)

- **난이도 실측 지도 (2번 완주 시점, 라인수 기준)**: portfolio 1412(svc872+repo540) ≫ transaction 1048(586+462) ≫ account 602(435+167) ≫ household 431 ≫ account_snapshot 371 ≫ 나머지. **곱씹을 알맹이는 3·4·6에 집중** — ▸account: `_calc_balance`/`_calc_cash_balance`/`_calc_investment_balance`(잔액 컬럼 없이 매번 거래 합산, 현금/투자 타입 분기) ▸transaction: `list_account_ledger`+`_ledger_start_balance`/`_split_ledger_cursor`/`_build_ledger_items`(원장 running balance를 커서 페이징과 결합 — 순서 의존 vs 부분조회 충돌) / `_signed_amount`(5타입 거래→계좌 기준 입출 부호) ▸portfolio: `_recalc_item_from_transactions`(평단 재계산 — 과거 매매 수정/삭제 시 거래 처음부터 replay) / `_recompute_realized_pnl`(실현손익). 1·2·7 + category/fixed/stats/home/wealth/settings/enum은 CRUD/조회/합성이라 알맹이 적음.

- **잔액 설계 (3번 account 결론)**: 통장에 `balance` 컬럼 없음 — `balance = start_balance + Σ거래`를 매 조회 재계산(거래가 source of truth, 잔액은 파생). 동기화 버그 구조적 차단이 대가는 집계쿼리 비용(배치로 상쇄). 공식 `_cash_flow`: income+ expense- transfer_out- transfer_in+ valuation_net(±부호는 집계단계에서 박음)+. **케이스를 통일한 설계**: 수동자산(부동산/연금/금/적금)을 VALUATION 거래로 표현 → 타입 분기 없이 현금계좌와 같은 공식 흡수. INVESTMENT만 "보유종목 평가액"이 진짜 다른 개념이라 유일 분기(`_calc_investment_balance` = 잔여현금(현금흐름−매수+매도) + Σ수량×현재가). 잘 짠 기준 = 케이스를 많이 처리한 게 아니라 케이스를 안 만들게 추상화 지점(=거래)을 잘 잡은 것. **단건/배치 이중구현**(`_calc_*` vs `_build_*`+`_load_balance_sources`)은 list N+1 막는 의도적 DRY 빚 — 순수함수(`_cash_flow`/`_summarize_holdings`)는 공유하고 "쿼리를 안에서 하냐/밖에서 받냐"만 다름.

- **전역 설계 6패턴** (소스분석 결론): ① ORM relationship 안 씀 → service에서 find_by_ids batch(N+1 회피) ② soft delete 기본('99') + 수동 bulk UPDATE cascade ③ household 스코프 강제(X-Household-Id + 멤버십), 소유권 위반은 NOT_FOUND로 은닉 ④ 모든 가격 KRW 박제(환율은 조회/갱신 시점 1회 곱함) ⑤ 커서 페이징 통일(평문 `{정렬키}|{id}`, limit+1) ⑥ overview 3종(home/wealth/settings)은 합성만(위임).
- **검증 에러 설계 (1번 발견)**: `CustomException(Exception)`은 일부러 `ValueError` 비상속. Pydantic v2는 validator가 던진 `ValueError/AssertionError`만 `ValidationError`로 흡수하고 그 외는 전파 → `CustomException`은 `RequestValidationError`(CM001로 뭉갬) 핸들러를 우회하고 전용 핸들러가 잡아 구체 코드(US003 등) 보존. status만으론 구분 안 되고(US003도 400) 프론트는 code로 i18n 매핑. 즉 "필드별 정확 메시지 필요하면 schema validator에서 `CustomException` 명시 던질 것"이 의도된 컨벤션(handlers.py:84 주석).

## 참고 링크
- 소스분석 학습 plan: `~/.claude/plans/eager-sparking-gadget.md`
- SRE 로드맵 plan: `~/.claude/plans/hashed-inventing-sprout.md`
