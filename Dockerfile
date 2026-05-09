FROM python:3.14-slim

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gosu && \
    rm -rf /var/lib/apt/lists/*

# 비root 사용자 생성
RUN useradd -m -s /bin/bash appuser

WORKDIR /app

# 의존성 파일 먼저 복사 → Docker 레이어 캐시 활용
COPY pyproject.toml uv.lock ./

# 프로덕션 의존성 설치
RUN uv sync --frozen

# 소스코드 복사
COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown -R appuser:appuser /app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
