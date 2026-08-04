"""冻结的已确认基础时长公式，不承担帧取整或连续冻结规则。"""

from __future__ import annotations

import math
from fractions import Fraction

from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.systems.reaction.frozen_constants import (
    FRAMES_PER_SECOND,
    FREEZE_DECAY_ACCELERATION_PER_SECOND,
    FREEZE_DECAY_RECOVERY_PER_SECOND,
    MIN_FREEZE_DECAY_RATE,
)
from genshin_sim.core.systems.reaction.models import FreezeResistanceObservation


def base_freeze_duration_seconds(frozen_amount: AuraAmount) -> float:
    """返回不含冻结抗性的基准冻结秒数。"""

    if not isinstance(frozen_amount, AuraAmount) or frozen_amount.is_zero:
        raise ValueError("frozen_amount 必须是正的 AuraAmount")
    return _duration_from_amount(float(frozen_amount.value), MIN_FREEZE_DECAY_RATE)


def frozen_amount_for_reaction_amount(reaction_amount: AuraAmount) -> AuraAmount:
    """冻结反应产生的冻元素量为实际反应量的两倍。"""

    if not isinstance(reaction_amount, AuraAmount) or reaction_amount.is_zero:
        raise ValueError("reaction_amount 必须是正的 AuraAmount")
    return reaction_amount * 2


def effective_frozen_amount(
    frozen_amount: AuraAmount,
    freeze_resistance: FreezeResistanceObservation,
) -> AuraAmount:
    """冻结抗性减少生成的冻元素量，而不是直接缩短时长。"""

    if not isinstance(frozen_amount, AuraAmount) or frozen_amount.is_zero:
        raise ValueError("frozen_amount 必须是正的 AuraAmount")
    if not isinstance(freeze_resistance, FreezeResistanceObservation):
        raise ValueError("freeze_resistance 必须是 FreezeResistanceObservation")
    return frozen_amount * (1 - freeze_resistance.value)


def remaining_frozen_amount(
    frozen_amount: AuraAmount,
    *,
    initial_decay_rate: float,
    frozen_seconds: Fraction | float,
) -> AuraAmount:
    """按匀加速衰减投影活动冻结的剩余冻元素量。"""

    if not isinstance(frozen_amount, AuraAmount) or frozen_amount.is_zero:
        raise ValueError("frozen_amount 必须是正的 AuraAmount")
    rate = _decay_rate(initial_decay_rate)
    seconds = _non_negative_fraction(frozen_seconds)
    consumed = Fraction(str(rate)) * seconds + (
        Fraction(str(FREEZE_DECAY_ACCELERATION_PER_SECOND)) * seconds**2 / 2
    )
    return frozen_amount - frozen_amount.minimum(consumed)


def freeze_duration_seconds(
    frozen_amount: AuraAmount,
    freeze_resistance: FreezeResistanceObservation,
    *,
    initial_decay_rate: float = MIN_FREEZE_DECAY_RATE,
) -> float:
    """以当前衰减速度计算冻结秒数，不承担帧取整或活动刷新量选择。"""

    if not isinstance(frozen_amount, AuraAmount) or frozen_amount.is_zero:
        raise ValueError("frozen_amount 必须是正的 AuraAmount")
    if not isinstance(freeze_resistance, FreezeResistanceObservation):
        raise ValueError("freeze_resistance 必须是 FreezeResistanceObservation")
    effective_amount = effective_frozen_amount(frozen_amount, freeze_resistance)
    if effective_amount.is_zero:
        return 0.0
    return _duration_from_amount(
        float(effective_amount.value),
        _decay_rate(initial_decay_rate),
    )


def increase_freeze_decay_rate(
    initial_decay_rate: float,
    frozen_seconds: float,
) -> float:
    """冻结活动期间按每秒 0.1 增加衰减速度。"""

    return _decay_rate(initial_decay_rate) + (
        FREEZE_DECAY_ACCELERATION_PER_SECOND * _non_negative_seconds(frozen_seconds)
    )


def recover_freeze_decay_rate(
    initial_decay_rate: float,
    thawed_seconds: float,
) -> float:
    """解冻后按每秒 0.2 恢复，最低回落到 0.4。"""

    return max(
        MIN_FREEZE_DECAY_RATE,
        _decay_rate(initial_decay_rate)
        - FREEZE_DECAY_RECOVERY_PER_SECOND * _non_negative_seconds(thawed_seconds),
    )


def freeze_duration_frames(duration_seconds: float) -> int:
    """按项目统一时间语义向上取整为帧；零时长保持为零帧。"""

    duration = _non_negative_seconds(duration_seconds)
    frames = duration * FRAMES_PER_SECOND
    nearest_frame = round(frames)
    # 抵消解析公式落在整数帧边界时的二进制浮点噪声，保持真实分数帧向上取整。
    if math.isclose(frames, nearest_frame, rel_tol=0.0, abs_tol=1e-9):
        return nearest_frame
    return math.ceil(frames)


def _duration_from_amount(frozen_amount: float, initial_decay_rate: float) -> float:
    # Integral of v(t) = initial_decay_rate + 0.1 * t equals frozen_amount.
    return (
        math.sqrt(initial_decay_rate**2 + 2 * FREEZE_DECAY_ACCELERATION_PER_SECOND * frozen_amount)
        - initial_decay_rate
    ) / FREEZE_DECAY_ACCELERATION_PER_SECOND


def _decay_rate(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("冻结衰减速度必须是数字")
    result = float(value)
    if not math.isfinite(result) or result < MIN_FREEZE_DECAY_RATE:
        raise ValueError("冻结衰减速度必须是有限数值且不低于 0.4")
    return result


def _non_negative_seconds(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("冻结经过时间必须是数字")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("冻结经过时间必须是有限非负数")
    return result


def _non_negative_fraction(value: Fraction | float) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, Fraction | int | float):
        raise ValueError("冻结经过时间必须是数字")
    result = value if isinstance(value, Fraction) else Fraction(str(value))
    if result < 0:
        raise ValueError("冻结经过时间必须是有限非负数")
    return result
