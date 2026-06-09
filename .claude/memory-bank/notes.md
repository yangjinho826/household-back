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

## 학습 노트
(이 프로젝트에서 배운 패턴/팁)

- **전역 설계 6패턴** (소스분석 결론): ① ORM relationship 안 씀 → service에서 find_by_ids batch(N+1 회피) ② soft delete 기본('99') + 수동 bulk UPDATE cascade ③ household 스코프 강제(X-Household-Id + 멤버십), 소유권 위반은 NOT_FOUND로 은닉 ④ 모든 가격 KRW 박제(환율은 조회/갱신 시점 1회 곱함) ⑤ 커서 페이징 통일(평문 `{정렬키}|{id}`, limit+1) ⑥ overview 3종(home/wealth/settings)은 합성만(위임).
- **검증 에러 설계 (1번 발견)**: `CustomException(Exception)`은 일부러 `ValueError` 비상속. Pydantic v2는 validator가 던진 `ValueError/AssertionError`만 `ValidationError`로 흡수하고 그 외는 전파 → `CustomException`은 `RequestValidationError`(CM001로 뭉갬) 핸들러를 우회하고 전용 핸들러가 잡아 구체 코드(US003 등) 보존. status만으론 구분 안 되고(US003도 400) 프론트는 code로 i18n 매핑. 즉 "필드별 정확 메시지 필요하면 schema validator에서 `CustomException` 명시 던질 것"이 의도된 컨벤션(handlers.py:84 주석).

## 참고 링크
- 소스분석 학습 plan: `~/.claude/plans/eager-sparking-gadget.md`
- SRE 로드맵 plan: `~/.claude/plans/hashed-inventing-sprout.md`
