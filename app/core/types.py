from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated

from pydantic import PlainSerializer


def _money(v: Decimal) -> float:
    return float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _quantity(v: Decimal) -> float:
    return float(v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


Money = Annotated[Decimal, PlainSerializer(_money, return_type=float)]
Rate = Annotated[Decimal, PlainSerializer(_money, return_type=float)]
Quantity = Annotated[Decimal, PlainSerializer(_quantity, return_type=float)]
# 거래통화 단가·환율 — 달러는 원화와 달리 소수부가 유의미해 4자리까지 보낸다.
# 직렬화 타입을 안 붙이면 Decimal 이 JSON **문자열**로 나가 프론트의 숫자 연산이 터진다.
Price = Annotated[Decimal, PlainSerializer(_quantity, return_type=float)]
