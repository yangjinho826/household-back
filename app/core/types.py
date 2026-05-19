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
