from __future__ import annotations

import math


class HealthState:
    """角色当前生命值状态。

    最大生命由属性系统解析；这里仅保存可变的当前生命。
    """

    __slots__ = ("_current_hp",)

    def __init__(self, current_hp: float | int) -> None:
        self.current_hp = current_hp

    @property
    def current_hp(self) -> float:
        return self._current_hp

    @current_hp.setter
    def current_hp(self, value: float | int) -> None:
        self._current_hp = _validate_current_hp(value)

    @property
    def is_zero(self) -> bool:
        return self.current_hp == 0.0


def _validate_current_hp(value: float | int) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = "当前生命值必须是数字"
        raise ValueError(msg)
    result = float(value)
    if not math.isfinite(result):
        msg = "当前生命值必须是有限数字"
        raise ValueError(msg)
    if result < 0:
        msg = "当前生命值不能为负数"
        raise ValueError(msg)
    if result == 0.0:
        return 0.0
    return result
