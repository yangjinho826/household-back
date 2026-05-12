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


settings = Settings()
