from enum import StrEnum


class TokenType(StrEnum):
    """JWT 토큰 타입"""

    ACCESS = "access"
    REFRESH = "refresh"
