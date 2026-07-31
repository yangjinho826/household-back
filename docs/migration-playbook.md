# Migration / Rollback Playbook

> 이 프로젝트의 롤백은 비대칭이다 — 이미지는 자동으로 돌아가지만 스키마는 안 돌아간다.
> 이 문서는 (1) 그 비대칭이 사고가 되지 않게 하는 마이그레이션 작성 원칙과
> (2) 그래도 사고가 났을 때의 판정·복구 절차를 정한다.

---

## 1. 현재 구조 — 왜 비대칭인가

| 단계 | 위치 | 동작 |
|---|---|---|
| 스키마 적용 | `entrypoint.sh` | 컨테이너 기동 시 `alembic upgrade head` 자동 실행 |
| 배포 게이트 | `deploy.yml` | guard(태그 ⊂ main) → test → **pre-deploy 스냅샷**(실패 시 배포 중단) → 배포 |
| 롤백 | `rollback.yml` | **incident 스냅샷** → 직전 timestamp 태그 이미지로 재기동. **DB는 건드리지 않음** |
| 스냅샷 2종 | R2 | `pre-deploy/` (배포 직전, 14일) · `pre-rollback/` (사고 시점, 14일) |

```
배포:  이미지 N-1 → N   +   스키마 head(N-1) → head(N)      ← 둘 다 자동
롤백:  이미지 N → N-1 (자동)  스키마는 head(N) 그대로        ← DB 복원은 수동
```

DDL이 적용된 뒤 앱이 실패하면, 이전 이미지로 돌려도 스키마는 새 버전이다.
따라서 롤백 가능성은 한 문장으로 환원된다:

> **직전 이미지(N-1)가 새 스키마(N) 위에서 그대로 돌 수 있는가.**

이게 성립하면 `rollback.yml` 하나로 모든 사고가 끝나고, DB 복원은 마지막 방어선으로 내려간다.
이 문서의 작성 원칙은 전부 이 한 줄을 지키기 위한 것이다.

단, 이 한 줄(앱 호환)과 별개로 entrypoint 자동 upgrade가 만드는 **기동 차원의 함정**이
하나 더 있다 — 리비전이 하나라도 추가된 배포는 additive여도 이미지 롤백 시 구 이미지가
못 뜬다. 5장 케이스 B 참조.

---

## 2. DDL 위험도 분류 — 지난 24개 이력 기준

| 분류 | 실제 리비전 예 | 구 이미지 호환 | 규칙 |
|---|---|---|---|
| **additive** (테이블/컬럼/인덱스 추가) | `7033d7e28bc7` (idempotency_records), `a7c3e9d1f4b8` (market_price_history), `9180adc92f4c` (currency_rates) | ✅ | 새 컬럼은 nullable 또는 `server_default` 필수 — 구 이미지의 INSERT가 그 컬럼을 모른다 |
| **widen** (타입 확장) | `d7e2f8a1b3c4` (tx type VARCHAR 20으로) | ✅ | 확장만. 축소(narrow)는 truncation 위험 — 금지 |
| **backfill** (데이터 채움) | `c3d5e7f9a1b2` (realized_pnl), `c8e1f4a7d2b9` (snapshot asof_balance) | ✅ | DDL과 같은 리비전에 섞지 않기 — 실패 시 원인 분리가 안 된다 |
| **drop** (컬럼/테이블 제거) | `a9668f7687a9` (fixed_expenses.amount), `a1c2e3f4b5d6`, `b2d3f4a5c6e7` | ❌ 구 이미지가 그 컬럼을 SELECT하면 즉사 | 코드 참조 제거가 **먼저 배포된 뒤**, 다음 배포에서 drop (contract 단계) |
| **rename** (in-place) | `e4a8b2c1f5d6` (ticker→name, symbol→code), `ae98f49a35f8` (country→market) | ❌ 구·신 이미지 중 한쪽은 반드시 죽는 컬럼명을 본다 | **in-place rename 금지** — add + copy + drop 3단계로 |

**주의 — 표의 ✅는 앱 호환 기준이다.** 리비전이 하나라도 추가된 배포는 additive여도
이미지 롤백 시 기동이 막힌다: 구 이미지의 Alembic이 DB에 기록된 새 리비전 ID를 자기
`alembic/versions/`에서 못 찾아 `Can't locate revision` 으로 죽는다 (runbook 케이스 B).

**정직한 이력**: 과거 rename 2건과 drop 3건은 단일 배포로 했다. 그 시점엔 이 playbook이
없었고, 사용자 2명·재기동 수 초 다운타임 허용 전제라 사고는 없었다.
"사고가 안 났다"와 "사고가 나도 안전하다"는 다르다 — 그 간극을 메우는 게 이 문서다.

---

## 3. 작성 원칙 — expand-contract

파괴적 변경(drop/rename/NOT NULL 추가/축소)은 한 배포에 넣지 않고 단계로 쪼갠다.
각 단계 직후 롤백해도 안전한지가 단계 나누기의 기준이다.

### rename: `old_col` → `new_col`

| 배포 | 스키마 | 코드 | 이 시점에 롤백하면 |
|---|---|---|---|
| N (expand) | `new_col` 추가 + 기존 값 copy | 계속 `old_col` 사용 (또는 dual-write) | 구 이미지는 `new_col`을 몰라도 돌아감 ✅ |
| N+1 (switch) | 변경 없음 | read/write를 `new_col`로 전환 | N 이미지는 `old_col`을 보는데 아직 있음 ✅ |
| N+2 (contract) | `old_col` drop | 변경 없음 | N+1 이미지는 이미 `new_col`만 씀 ✅ |

### NOT NULL 컬럼 추가

| 배포 | 동작 |
|---|---|
| N | nullable(또는 `server_default`)로 추가 + backfill |
| N+1 | `ALTER ... SET NOT NULL` (코드가 항상 값을 쓰는 걸 확인한 뒤) |

### 비용 조절 — 전부 쪼개진 않는다

1인 운영에서 배포 횟수 3배는 실질 비용이다. 단계 강제는 **표 2의 ❌ 분류(파괴적 DDL)에만** 적용한다.

- 아직 코드 어디서도 참조 안 하는 신규 테이블/컬럼 → 단일 배포 자유
- additive/widen/backfill → 단일 배포 자유 (각 규칙만 지키면 구 이미지 호환이 이미 성립)

---

## 4. `downgrade()`의 위치 — 운영 롤백 수단이 아니다

모든 리비전에 `downgrade()`가 구현돼 있지만, 용도는 로컬 개발 되감기다.

```python
# a9668f7687a9 의 downgrade — 컬럼은 돌아오지만 데이터는 안 돌아온다
def downgrade() -> None:
    op.add_column("fixed_expenses",
        sa.Column("amount", sa.Numeric(15, 2), nullable=False, server_default="0"))
    # ↑ drop 시점에 소실된 실제 금액이 전부 0 으로 채워진다
```

운영에서 스키마를 되돌려야 하면 `alembic downgrade`가 아니라 **pre-deploy 스냅샷 복원**이다.
스냅샷은 스키마와 데이터를 같은 시점으로 함께 되돌린다 — downgrade는 스키마만 되돌리고
데이터 정합성은 보장하지 않는다.

---

## 5. 사고 runbook — 배포 후 앱 실패 시

### 0. 판정: 이번 배포에 DDL이 있었나

```bash
git diff <직전-태그> <이번-태그> -- alembic/versions/
```

### 케이스 A — 새 리비전 없음 (코드만 변경)

`rollback.yml` 실행으로 끝. DB는 건드리지 않는다.

### 케이스 B — additive/widen/backfill 리비전 동반

표 2 기준 앱은 호환이지만 **구 이미지가 기동을 못 한다** — entrypoint의
`alembic upgrade head`가 DB에 기록된 새 리비전을 자기 스크립트에서 못 찾아
`Can't locate revision` 으로 죽고 재시작 루프에 빠진다.

1. **기본 대응 = roll-forward** — 원인을 고쳐 새 태그로 재배포. 스키마는 additive라
   그대로 둬도 안전하고, 수동 DB 조작이 없어 실수 여지가 가장 적다.
2. 앱이 죽어 있어 즉시 복구가 급하면 — `alembic_version` 수동 왕복:

   ```sql
   -- 구 이미지 기동 전: 리비전 포인터만 구 head 로 (잔재 컬럼은 구 앱에 무해)
   UPDATE alembic_version SET version_num = '<구 head>';
   ```

   **왕복 의무**: 이 상태에서 나중에 신 버전을 재배포하면 upgrade가 같은 DDL을
   재적용하려다 충돌한다(column already exists). 스키마는 이미 신 상태이므로,
   재배포 직전 `version_num`을 다시 신 head로 되돌려야 한다. 잊기 쉬운 수동
   절차라서 여유가 있으면 항상 1번(roll-forward)이 우선.

### 케이스 C — 파괴적 DDL(drop/rename/축소) 동반

1. **`rollback.yml` 먼저 실행** — incident 스냅샷(`pre-rollback/`)이 자동 확보된다.
   구 이미지는 어차피 못 뜬다(케이스 B와 같은 `Can't locate revision` + 없어진
   컬럼 참조) — 목적은 재기동이 아니라 스냅샷 확보다. 앱 중단을 감수하고 2번으로.
2. **pre-deploy 스냅샷 복원** — 배포 직전 상태로 스키마+데이터를 함께 되돌린다.

   ```bash
   # 복원 대상 확인 (배포 직전본 — 파일명에 이미지 태그가 박혀 있다)
   rclone lsf r2:$R2_BUCKET/pre-deploy/ | sort | tail -1
   ```

   복원 절차 자체는 `infra/backup/README.md` "복구" 섹션 그대로 —
   임시 DB에 먼저 복구·검증 후 운영 swap. 자동화 경계도 동일하다:
   **임시 DB 검증까지가 자동, 운영 swap은 사람이 결정한다** (`restore-drill.sh`와 같은 철학).
3. **복원 + 구 이미지 조합은 자기일관적** — 복원된 덤프의 `alembic_version`이 구 head라,
   구 이미지가 기동하며 실행하는 `alembic upgrade head`는 no-op이다. 별도 조치 불필요.
4. **유실 창 정산** — pre-deploy 복원은 배포~사고 사이의 쓰기를 버린다.
   incident 스냅샷(`pre-rollback/`)과 대조해 그 구간의 유실분을 확인하고 머지 여부를 판단한다.

### 케이스 D — 마이그레이션 자체가 실패 (앱이 안 뜸)

`upgrade()` 도중 실패하면 Alembic은 해당 리비전을 트랜잭션으로 감싸므로
(PostgreSQL은 transactional DDL) `alembic_version`은 이전 리비전에 머문다.
컨테이너는 재시작 루프 → UptimeRobot이 서버 다운으로 감지.
원인 수정 후 재배포가 기본. 스키마가 반쯤 적용된 상태는 아니므로 DB 복원은 불필요.
단, 리비전 안에서 `op.execute`로 autocommit을 강제했거나 `CREATE INDEX CONCURRENTLY`처럼
트랜잭션 밖 DDL을 쓴 경우는 예외 — 그런 리비전은 현재 24개 중 없다.

---

## 6. 마이그레이션 PR 체크리스트

- [ ] 이 DDL은 표 2의 어느 분류인가 — ❌ 분류면 expand-contract 단계로 쪼갰나
- [ ] 새 컬럼에 nullable 또는 `server_default`가 있나
- [ ] DDL과 backfill이 한 리비전에 섞여 있지 않나
- [ ] "직전 이미지가 이 스키마에서 돌 수 있나"에 예라고 답할 수 있나

---

## 7. 감수한 한계

- **playbook은 문서지 강제가 아니다** — 지키는 건 PR 체크리스트를 쓰는 사람 규율에 의존한다.
  파괴적 DDL을 CI에서 감지하는 lint(예: `op.drop_column`/`new_column_name` grep)는 로드맵 옵션.
- **pre-deploy 복원의 유실 창** — 배포~사고 사이 쓰기는 incident 스냅샷과의 수동 머지로만
  구제된다. 머지 규칙(특히 idempotency_records 같은 시스템 테이블)은 케이스별 판단.
- **expand-contract의 dual-write 구간** — copy 마이그레이션 이후 switch 배포 전까지
  구 컬럼에만 쓰인 값은 switch 시점에 재copy가 필요할 수 있다. 이 규모(쓰기 빈도 낮음)에선
  switch 배포 직전 수동 재copy로 충분하다고 판단.
