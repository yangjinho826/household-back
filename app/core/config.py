from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 설정"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "household"
    DEBUG: bool = False
    PORT: int = 9000

    # DB 접속
    DATABASE_URL: str = ""

    # 커넥션 풀
    DB_POOL_MIN: int = 10
    DB_POOL_MAX: int = 20
    DB_POOL_TIMEOUT: int = 30

    # 로깅
    LOG_LEVEL: str = "INFO"

    # CORS
    ALLOWED_ORIGINS: list[str] = ["*"]

    # JWT
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION: int = 1800  # access token: 30분
    JWT_REFRESH_EXPIRATION: int = 604800  # refresh token: 7일

    # 쿠키 — HTTPS 환경에서만 True. HTTP 운영이면 임시로 False.
    COOKIE_SECURE: bool = True

    # 장애 알림 — 빈 값이면 알림 비활성 (앱 동작에는 영향 없음)
    DISCORD_WEBHOOK_URL: str = ""

    # 데모 가계부 — 이력서 공개용 체험 계정. 운영에서만 켠다.
    # 기본값이 False 인 게 중요: 테스트는 실제 uvicorn 을 띄워 lifespan 을 태우므로
    # 켜져 있으면 매 테스트 기동마다 시딩이 돌아 게이트가 오염된다.
    DEMO_SEED_ENABLED: bool = False
    DEMO_EMAIL: str = "moeum@gmail.com"
    DEMO_PASSWORD: str = "moeum2026"

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        # 빈 값 / 너무 짧은 값으로 부팅되면 발급한 토큰 검증이 일관되지 않거나
        # 보안이 약해짐. 배포 시 .env 누락을 부팅 단계에서 차단.
        if not v or len(v) < 32:
            raise ValueError(
                "JWT_SECRET 환경변수가 비어 있거나 32자 미만입니다",
            )
        return v


settings = Settings()
