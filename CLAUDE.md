# household-back

스택: `ai-router-api`

## 적용 룰

<!-- ~/.claude/rules/ 의 룰 파일들을 @import. claude-init 이 자동 생성 -->

<!-- common -->
@~/.claude/rules/common/README.md
@~/.claude/rules/common/coding.md
@~/.claude/rules/common/git.md
@~/.claude/rules/common/style.md

<!-- python -->
@~/.claude/rules/python/README.md
@~/.claude/rules/python/style.md
@~/.claude/rules/python/testing.md

<!-- python-fastapi -->
@~/.claude/rules/python-fastapi/README.md
@~/.claude/rules/python-fastapi/general.md
@~/.claude/rules/python-fastapi/sqlalchemy.md
@~/.claude/rules/python-fastapi/testing.md

<!-- cnnet -->
@~/.claude/rules/cnnet/README.md
@~/.claude/rules/cnnet/general.md

<!-- ai-router-api -->
@~/.claude/rules/ai-router-api/README.md
@~/.claude/rules/ai-router-api/general.md

## 빌드/실행

```bash
uv sync
uv run pytest
uv run uvicorn app.main:app --reload
docker compose -f docker-compose.yml up
```

## 프로젝트 메모

- 패키지명: household
- ai-router-api 스택 그대로 (FastAPI / SQLAlchemy 2.0 / asyncpg / JWT)
- Docker: docker-compose-dev.yml / docker-compose.yml
- 호스팅: Oracle Cloud Free Tier (ARM)
- 프론트: household-front (Next.js, 별도 레포)

## MVP — 가계부

부부 공유 가능한 가계부 앱. 노션 가계부 대체.

### 도메인 (10 테이블)

```
User 단위
├─ users
├─ households            가계부 그룹
└─ household_members     n:n 멤버십

가계부 종속
├─ accounts              통장 (account_type: 생활 | 적립 | 투자)
├─ categories            kind: expense | income
├─ transactions          tx_type: expense | income | transfer
└─ fixed_expenses        고정지출 참조 목록

통장 종속
├─ portfolio_items       보유 종목
└─ account_snapshots     월말 잔액 (사용자 수동 저장)

종목 종속
└─ portfolio_value_history   월별 평가액 추이
```