-- =============================================================================
-- 가계부 MVP — PostgreSQL Schema
-- =============================================================================
-- 모든 비즈니스 로직 / 검증 / 무결성 / 참조 관계는 FastAPI service 레이어에서 처리.
-- DB는 테이블 / 인덱스만 책임.
--
-- 표준 공통 컬럼 (모든 테이블 BaseEntity 상속):
--   id              UUID         PK (uuid.uuid4 기본값)
--   data_stat_cd    VARCHAR(30)  데이터 상태 코드
--   frst_reg_dt     TIMESTAMPTZ  최초 등록 일시
--   last_mdfcn_dt   TIMESTAMPTZ  최종 수정 일시
-- =============================================================================


-- =============================================================================
-- 1. users — 사용자
-- =============================================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY,
    email           VARCHAR(255) NOT NULL,
    name            VARCHAR(100) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    language        VARCHAR(10) NOT NULL,
    data_stat_cd    VARCHAR(30) NOT NULL,
    frst_reg_dt     TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_users_email ON users(email);


-- =============================================================================
-- 2. households — 가계부 그룹
-- =============================================================================
CREATE TABLE households (
    id              UUID PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    description     TEXT,
    owner_id        UUID NOT NULL,    -- logical FK -> users.id
    currency        CHAR(3) NOT NULL,
    started_at      DATE NOT NULL,
    data_stat_cd    VARCHAR(30) NOT NULL,
    frst_reg_dt     TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_households_owner ON households(owner_id);


-- =============================================================================
-- 3. household_members — 가계부 멤버십
-- =============================================================================
CREATE TABLE household_members (
    id              UUID PRIMARY KEY,
    household_id    UUID NOT NULL,    -- logical FK -> households.id
    user_id         UUID NOT NULL,    -- logical FK -> users.id
    role            VARCHAR(20) NOT NULL,
    joined_at       TIMESTAMPTZ NOT NULL,
    data_stat_cd    VARCHAR(30) NOT NULL,
    frst_reg_dt     TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_members_user ON household_members(user_id);
CREATE INDEX idx_members_household ON household_members(household_id);


-- =============================================================================
-- 4. accounts — 통장
-- =============================================================================
CREATE TABLE accounts (
    id              UUID PRIMARY KEY,
    household_id    UUID NOT NULL,    -- logical FK -> households.id
    name            VARCHAR(100) NOT NULL,
    account_type    VARCHAR(20) NOT NULL,
    start_balance   NUMERIC(15, 2) NOT NULL,
    color           VARCHAR(7),
    icon            VARCHAR(50),
    sort_order      INT NOT NULL,
    is_archived     BOOLEAN NOT NULL,
    data_stat_cd    VARCHAR(30) NOT NULL,
    frst_reg_dt     TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_accounts_household ON accounts(household_id);


-- =============================================================================
-- 5. categories — 카테고리 (지출 / 수입)
-- =============================================================================
CREATE TABLE categories (
    id              UUID PRIMARY KEY,
    household_id    UUID NOT NULL,    -- logical FK -> households.id
    kind            VARCHAR(10) NOT NULL,
    name            VARCHAR(100) NOT NULL,
    color           VARCHAR(7),
    icon            VARCHAR(50),
    sort_order      INT NOT NULL,
    is_archived     BOOLEAN NOT NULL,
    data_stat_cd    VARCHAR(30) NOT NULL,
    frst_reg_dt     TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_categories_household ON categories(household_id, kind);


-- =============================================================================
-- 6. transactions — 거래 (지출 / 수입 / 이체 통합)
-- =============================================================================
CREATE TABLE transactions (
    id                  UUID PRIMARY KEY,
    household_id        UUID NOT NULL,    -- logical FK -> households.id
    tx_type             VARCHAR(10) NOT NULL,
    amount              NUMERIC(15, 2) NOT NULL,
    tx_date             DATE NOT NULL,
    account_id          UUID NOT NULL,    -- logical FK -> accounts.id
    to_account_id       UUID,             -- logical FK -> accounts.id (transfer 시만)
    category_id         UUID,             -- logical FK -> categories.id
    paid_by_user_id     UUID,             -- logical FK -> users.id
    is_fixed            BOOLEAN NOT NULL,
    memo                TEXT,
    data_stat_cd        VARCHAR(30) NOT NULL,
    frst_reg_dt         TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt       TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_tx_household_date ON transactions(household_id, tx_date DESC);
CREATE INDEX idx_tx_account ON transactions(account_id);
CREATE INDEX idx_tx_to_account ON transactions(to_account_id);
CREATE INDEX idx_tx_category ON transactions(category_id);
CREATE INDEX idx_tx_date ON transactions(tx_date DESC);


-- =============================================================================
-- 7. fixed_expenses — 고정지출 참조 목록
-- =============================================================================
CREATE TABLE fixed_expenses (
    id              UUID PRIMARY KEY,
    household_id    UUID NOT NULL,    -- logical FK -> households.id
    name            VARCHAR(100) NOT NULL,
    day_of_month    INT NOT NULL,
    category_id     UUID,             -- logical FK -> categories.id
    color           VARCHAR(7),
    icon            VARCHAR(50),
    sort_order      INT NOT NULL,
    is_archived     BOOLEAN NOT NULL,
    data_stat_cd    VARCHAR(30) NOT NULL,
    frst_reg_dt     TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_fixed_household ON fixed_expenses(household_id);


-- =============================================================================
-- 8. portfolio_items — 보유 종목
-- =============================================================================
CREATE TABLE portfolio_items (
    id              UUID PRIMARY KEY,
    household_id    UUID NOT NULL,    -- logical FK -> households.id
    account_id      UUID NOT NULL,    -- logical FK -> accounts.id (broker)
    ticker          VARCHAR(100) NOT NULL,
    symbol          VARCHAR(50),
    quantity        NUMERIC(15, 4) NOT NULL,
    avg_price       NUMERIC(15, 2) NOT NULL,
    current_price   NUMERIC(15, 2) NOT NULL,
    is_archived     BOOLEAN NOT NULL,
    data_stat_cd    VARCHAR(30) NOT NULL,
    frst_reg_dt     TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_portfolio_household ON portfolio_items(household_id);
CREATE INDEX idx_portfolio_account ON portfolio_items(account_id);


-- =============================================================================
-- 8-1. portfolio_transactions — 자산 거래 이력 (매수/매도)
-- =============================================================================
CREATE TABLE portfolio_transactions (
    id                UUID PRIMARY KEY,
    household_id      UUID NOT NULL,    -- logical FK -> households.id
    account_id        UUID NOT NULL,    -- logical FK -> accounts.id (broker)
    portfolio_item_id UUID,             -- logical FK -> portfolio_items.id (nullable)
    ticker            VARCHAR(100) NOT NULL,
    symbol            VARCHAR(50),
    pt_type           VARCHAR(10) NOT NULL,    -- BUY / SELL
    quantity          NUMERIC(15, 4) NOT NULL,
    price             NUMERIC(15, 2) NOT NULL, -- 단가 (per unit)
    tx_date           DATE NOT NULL,
    memo              TEXT,
    data_stat_cd      VARCHAR(30) NOT NULL,
    frst_reg_dt       TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt     TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_pt_household_date ON portfolio_transactions(household_id, tx_date DESC);
CREATE INDEX idx_pt_account ON portfolio_transactions(account_id);
CREATE INDEX idx_pt_item ON portfolio_transactions(portfolio_item_id);


-- =============================================================================
-- 9. portfolio_value_history — 종목 평가액 추이 (월별)
-- =============================================================================
CREATE TABLE portfolio_value_history (
    id                  UUID PRIMARY KEY,
    household_id        UUID NOT NULL,    -- logical FK -> households.id
    account_id          UUID NOT NULL,    -- logical FK -> accounts.id
    portfolio_item_id   UUID NOT NULL,    -- logical FK -> portfolio_items.id
    snapshot_date       DATE NOT NULL,
    quantity            NUMERIC(15, 4) NOT NULL,
    avg_price           NUMERIC(15, 2) NOT NULL,
    current_price       NUMERIC(15, 2) NOT NULL,
    cost                NUMERIC(15, 2) NOT NULL,
    valuation           NUMERIC(15, 2) NOT NULL,
    data_stat_cd        VARCHAR(30) NOT NULL,
    frst_reg_dt         TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt       TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_pvh_household ON portfolio_value_history(household_id);
CREATE INDEX idx_pvh_account ON portfolio_value_history(account_id);
CREATE INDEX idx_pvh_item_date ON portfolio_value_history(portfolio_item_id, snapshot_date DESC);


-- =============================================================================
-- 10. account_snapshots — 월말 통장 잔액 스냅샷
-- =============================================================================
CREATE TABLE account_snapshots (
    id              UUID PRIMARY KEY,
    account_id      UUID NOT NULL,    -- logical FK -> accounts.id
    snapshot_date   DATE NOT NULL,
    balance         NUMERIC(15, 2) NOT NULL,
    data_stat_cd    VARCHAR(30) NOT NULL,
    frst_reg_dt     TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_snapshots_account_date ON account_snapshots(account_id, snapshot_date DESC);
CREATE INDEX idx_snapshots_date ON account_snapshots(snapshot_date DESC);


-- =============================================================================
-- 11. refresh_tokens — JWT refresh token
-- =============================================================================
CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY,
    user_id         UUID NOT NULL,    -- logical FK -> users.id
    token           VARCHAR(512) NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    data_stat_cd    VARCHAR(30) NOT NULL,
    frst_reg_dt     TIMESTAMPTZ NOT NULL,
    last_mdfcn_dt   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token ON refresh_tokens(token);