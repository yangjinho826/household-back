from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """비밀번호를 bcrypt로 해싱

    Args:
        password: 평문 비밀번호

    Returns:
        해싱된 비밀번호 문자열
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """평문 비밀번호와 해시값 일치 여부 검증

    Args:
        plain_password: 평문 비밀번호
        hashed_password: 해싱된 비밀번호

    Returns:
        일치 여부
    """
    return pwd_context.verify(plain_password, hashed_password)
