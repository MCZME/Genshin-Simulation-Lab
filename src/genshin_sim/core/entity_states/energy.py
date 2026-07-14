from __future__ import annotations

import math


class EnergyState:
    """角色当前标准元素能量的最小可变状态。"""

    __slots__ = ("_current_energy",)

    def __init__(self, current_energy: float | int = 0.0) -> None:
        self.current_energy = current_energy

    @property
    def current_energy(self) -> float:
        return self._current_energy

    @current_energy.setter
    def current_energy(self, value: float | int) -> None:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("当前元素能量必须是数字")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("当前元素能量必须是有限数字")
        if result < 0:
            raise ValueError("当前元素能量不能为负数")
        self._current_energy = 0.0 if result == 0.0 else result
