-- 62cfbbe6 가계부 화면 확인용 — 과거 자산 스냅샷 역산 시드.
-- 2026-04-01 박제값(잔액)을 기준으로 월별 ratio 를 곱해 2025-10 ~ 2026-05 를 만든다.
-- 추이 차트 + 전월대비 증감 + 계좌별 리포트(월별 수입/지출 차트)까지 보이게 하는 용도.
-- monthly_income/expense 는 실데이터가 0 이라 잔액 기반 그럴듯한 값으로 채운다(화면 확인용).
-- 재실행 안전: 대상 월(4월 원본 제외)을 먼저 지우고 다시 넣고, 4월은 monthly 만 보강.

\set hh '62cfbbe6-f3df-4aa2-8f30-eb9ec4dd8c58'

BEGIN;

-- 이전 시드분 정리 (4월 원본 잔액은 보존 — 기준값)
DELETE FROM account_snapshots s
USING accounts a
WHERE s.account_id = a.id
  AND a.household_id = :'hh'
  AND s.snapshot_date BETWEEN '2025-10-01' AND '2026-05-01'
  AND s.snapshot_date <> '2026-04-01';

-- 월별 역산: (대상월, 4월 대비 비율). 톱니 우상향 + 5월(현재 수준) 추가.
-- monthly_income/expense/fixed = 그달 잔액 기반 비율 (수입>지출 으로 우상향 느낌).
INSERT INTO account_snapshots
  (id, account_id, snapshot_date, balance,
   monthly_income, monthly_expense, monthly_fixed_expense,
   frst_reg_dt, last_mdfcn_dt, data_stat_cd)
SELECT
  gen_random_uuid(),
  s.account_id,
  m.target::date,
  round(s.balance * m.ratio, 2),
  round(s.balance * m.ratio * 0.08, 2),  -- 수입 ≈ 잔액의 8%
  round(s.balance * m.ratio * 0.05, 2),  -- 지출 ≈ 5%
  round(s.balance * m.ratio * 0.02, 2),  -- 고정지출 ≈ 2%
  now(), now(), s.data_stat_cd
FROM account_snapshots s
JOIN accounts a ON a.id = s.account_id
CROSS JOIN (VALUES
  ('2025-10-01', 0.40),  -- 바닥
  ('2025-11-01', 0.60),  -- ↑
  ('2025-12-01', 0.50),  -- ↓ (10월보단 위)
  ('2026-01-01', 0.75),  -- ↑
  ('2026-02-01', 0.65),  -- ↓ (12월보단 위)
  ('2026-03-01', 0.90),  -- ↑
  ('2026-05-01', 1.00)   -- 4월 원본(1.0)과 같은 현재 수준
) AS m(target, ratio)
WHERE a.household_id = :'hh'
  AND s.snapshot_date = '2026-04-01';

-- 4월 원본은 잔액 유지하고 monthly 만 보강 (실데이터가 0 이라 차트가 비어 보임 방지)
UPDATE account_snapshots s SET
  monthly_income = round(s.balance * 0.08, 2),
  monthly_expense = round(s.balance * 0.05, 2),
  monthly_fixed_expense = round(s.balance * 0.02, 2)
FROM accounts a
WHERE s.account_id = a.id
  AND a.household_id = :'hh'
  AND s.snapshot_date = '2026-04-01';

COMMIT;

-- 검증: 월별 총자산 + 수입/지출 추이
SELECT s.snapshot_date, count(*) AS accs,
       sum(s.balance) AS total_balance,
       sum(s.monthly_income) AS income,
       sum(s.monthly_expense) AS expense
FROM account_snapshots s
JOIN accounts a ON a.id = s.account_id
WHERE a.household_id = :'hh'
GROUP BY s.snapshot_date
ORDER BY s.snapshot_date;
