# household-back

스택: `python-fastapi`

<!-- BEGIN claude-init managed: rules -->
## 적용 룰

<!-- 글로벌 룰은 ~/.claude/lazy-rules/ (@import 로 로드 — 디렉토리 자동 로드 X), 외부 룰은 ~/.claude-rules-store/ (@import 로만 로드). claude-init 이 자동 생성/갱신 -->

<!-- common -->
@~/.claude/lazy-rules/common/README.md
@~/.claude/lazy-rules/common/coding.md
@~/.claude/lazy-rules/common/git.md
@~/.claude/lazy-rules/common/style.md

<!-- python -->
@~/.claude/lazy-rules/python/README.md
@~/.claude/lazy-rules/python/style.md
@~/.claude/lazy-rules/python/testing.md

<!-- python-fastapi -->
@~/.claude/lazy-rules/python-fastapi/README.md
@~/.claude/lazy-rules/python-fastapi/general.md
@~/.claude/lazy-rules/python-fastapi/sqlalchemy.md
@~/.claude/lazy-rules/python-fastapi/testing.md

<!-- END claude-init managed: rules -->

## 빌드/실행

```bash
uv sync
uv run pytest
uv run uvicorn app.main:app --reload
```

## 프로젝트 메모

<!-- 프로젝트 고유 컨벤션을 여기에 추가 -->
<!-- 예시:
- DB: PostgreSQL + asyncpg
- 마이그레이션: alembic
- 캐시: Redis
- 인증: JWT (Access 30분 / Refresh 14일)
-->
