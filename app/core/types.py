from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated

from pydantic import PlainSerializer


def _format(v: Decimal, scale: str) -> str:
    return format(v.quantize(Decimal(scale), rounding=ROUND_HALF_UP), "f")


def _money(v: Decimal) -> str:
    return _format(v, "0.01")


def _quantity(v: Decimal) -> str:
    return _format(v, "0.0001")


Money = Annotated[Decimal, PlainSerializer(_money, return_type=str)]
Rate = Annotated[Decimal, PlainSerializer(_money, return_type=str)]
Quantity = Annotated[Decimal, PlainSerializer(_quantity, return_type=str)]
