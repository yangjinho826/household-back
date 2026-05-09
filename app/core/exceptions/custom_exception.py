from app.core.exceptions.error_code import ErrorCode


class CustomException(Exception):
    """비즈니스 로직 예외 — ErrorCode와 함께 사용"""

    def __init__(self, error_code: ErrorCode, message: str | None = None) -> None:
        self.error_code = error_code
        self.message = message or error_code.message
        super().__init__(self.message)
