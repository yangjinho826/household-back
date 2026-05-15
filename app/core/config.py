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

    # 스케줄러 — 운영 단일 인스턴스에서만 true. 다중 워커일 때도 advisory lock 안전망 작동.
    SCHEDULER_ENABLED: bool = False

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
