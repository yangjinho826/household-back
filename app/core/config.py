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
    PORT: int = 8000

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
    JWT_EXPIRATION: int = 900
    JWT_REFRESH_EXPIRATION: int = 604800


settings = Settings()
