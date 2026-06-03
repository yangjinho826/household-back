import asyncio

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def hash_password(password: str) -> str:
    """비밀번호를 bcrypt로 해싱.

    bcrypt 는 CPU 집약(의도적으로 느림)이라 to_thread 로 오프로드해
    async 이벤트 루프를 막지 않는다.
    """
    return await asyncio.to_thread(pwd_context.hash, password)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """평문 비밀번호와 해시값 일치 여부 검증 (이벤트 루프 보호 위해 to_thread)."""
    return await asyncio.to_thread(pwd_context.verify, plain_password, hashed_password)
