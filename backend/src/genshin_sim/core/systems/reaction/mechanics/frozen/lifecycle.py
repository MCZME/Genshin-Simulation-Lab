"""冻结活动与恢复状态的帧投影纯函数。"""

from __future__ import annotations

from fractions import Fraction

from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.systems.reaction.frozen_constants import FRAMES_PER_SECOND
from genshin_sim.core.systems.reaction.mechanics.frozen.formulas import (
    freeze_duration_frames,
    freeze_duration_seconds,
    increase_freeze_decay_rate,
    recover_freeze_decay_rate,
    remaining_frozen_amount,
)
from genshin_sim.core.systems.reaction.models import FreezeResistanceObservation
from genshin_sim.core.systems.reaction.states import (
    FreezeRecoveryState,
    FrozenState,
)


def active_freeze_decay_rate_at(state: FrozenState, frame: int) -> float:
    """投影活动冻结在给定帧的衰减速率，不修改 State。"""

    updated_frame = _frozen_rate_updated_frame(state)
    _frame_not_before(frame, updated_frame)
    return increase_freeze_decay_rate(
        state.decay_rate,
        (frame - updated_frame) / FRAMES_PER_SECOND,
    )


def active_frozen_amount_at(
    state: FrozenState,
    frozen_amount: AuraAmount,
    frame: int,
) -> AuraAmount:
    """投影活动冻结在给定帧的剩余冻元素量，不修改 Aura 或 State。"""

    updated_frame = _frozen_rate_updated_frame(state)
    _frame_not_before(frame, updated_frame)
    return remaining_frozen_amount(
        frozen_amount,
        initial_decay_rate=state.decay_rate,
        frozen_seconds=Fraction(frame - updated_frame, FRAMES_PER_SECOND),
    )


def recovered_freeze_decay_rate_at(state: FreezeRecoveryState, frame: int) -> float:
    """投影解冻后的衰减速率，不修改 State。"""

    _frame_not_before(frame, state.decay_rate_updated_frame)
    return recover_freeze_decay_rate(
        state.decay_rate,
        (frame - state.decay_rate_updated_frame) / FRAMES_PER_SECOND,
    )


def freeze_expiry_frame(
    *,
    frame: int,
    frozen_amount: AuraAmount,
    freeze_resistance: FreezeResistanceObservation,
    initial_decay_rate: float,
) -> int:
    """按统一向上取整帧语义计算活动冻结的半开区间终点。"""

    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise ValueError("frame 必须是非负整数")
    duration = freeze_duration_seconds(
        frozen_amount,
        freeze_resistance,
        initial_decay_rate=initial_decay_rate,
    )
    return frame + freeze_duration_frames(duration)


def _frame_not_before(frame: int, lower_bound: int) -> None:
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < lower_bound:
        raise ValueError("frame 不能早于状态的 decay_rate_updated_frame")


def _frozen_rate_updated_frame(state: FrozenState) -> int:
    if state.decay_rate_updated_frame is None:
        raise RuntimeError("FrozenState 初始化后必须具有 decay_rate_updated_frame")
    return state.decay_rate_updated_frame
