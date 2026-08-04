"""Aura、ICD 与 Reaction 使用的精确元素量。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Self


def _fraction(value: AuraAmount | Fraction | int | float | str) -> Fraction:
    if isinstance(value, AuraAmount):
        return value.value
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        raise TypeError("AuraAmount 不能由布尔值创建")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("AuraAmount 必须是有限数值")
        return Fraction(str(value))
    if isinstance(value, int | str):
        return Fraction(value)
    raise TypeError("AuraAmount 必须使用精确数值创建")


@dataclass(frozen=True, order=True, slots=True)
class AuraAmount:
    """非负有理元素量，并提供稳定序列化。"""

    value: Fraction

    def __init__(self, value: AuraAmount | Fraction | int | float | str = 0) -> None:
        fraction = _fraction(value)
        if fraction < 0:
            raise ValueError("AuraAmount 不能为负数")
        object.__setattr__(self, "value", fraction)

    @classmethod
    def zero(cls) -> Self:
        return cls(0)

    @classmethod
    def one(cls) -> Self:
        return cls(1)

    @property
    def numerator(self) -> int:
        return self.value.numerator

    @property
    def denominator(self) -> int:
        return self.value.denominator

    @property
    def decimal(self) -> float:
        return float(self.value)

    @property
    def is_zero(self) -> bool:
        return self.value == 0

    def __add__(self, other: AuraAmount | Fraction | int | float | str) -> AuraAmount:
        return AuraAmount(self.value + _fraction(other))

    def __sub__(self, other: AuraAmount | Fraction | int | float | str) -> AuraAmount:
        result = self.value - _fraction(other)
        if result < 0:
            raise ValueError("AuraAmount 相减后不能为负数")
        return AuraAmount(result)

    def __mul__(self, other: AuraAmount | Fraction | int | float | str) -> AuraAmount:
        result = self.value * _fraction(other)
        if result < 0:
            raise ValueError("AuraAmount 相乘后不能为负数")
        return AuraAmount(result)

    def __truediv__(self, other: AuraAmount | Fraction | int | float | str) -> AuraAmount:
        divisor = _fraction(other)
        if divisor <= 0:
            raise ValueError("AuraAmount 除数必须为正数")
        return AuraAmount(self.value / divisor)

    def minimum(self, other: AuraAmount | Fraction | int | float | str) -> AuraAmount:
        return AuraAmount(min(self.value, _fraction(other)))

    def maximum(self, other: AuraAmount | Fraction | int | float | str) -> AuraAmount:
        return AuraAmount(max(self.value, _fraction(other)))

    def to_dict(self) -> dict[str, int | float]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "decimal": self.decimal,
        }

    def __str__(self) -> str:
        return str(self.value)
