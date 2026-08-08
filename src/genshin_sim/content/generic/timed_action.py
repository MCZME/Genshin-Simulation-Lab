"""generic 定时动作规格与统一动作编译。

``TimedActionSpec`` 描述一个定时动作的数据（帧表、命中点、衔接表），既用作
普攻连段的一段，也用作链外独立动作（重击、战技、爆发、跳跃等）；
``build_timed_actions`` 统一把规格编译为 core 的 ``TimedImpactAction``。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from genshin_sim.core.actions import TargetingSpec, TimedImpactAction


class TimedActionSpecError(Exception):
    """定时动作规格错误基类。"""


class TimedActionSpecValidationError(TimedActionSpecError, ValueError):
    """定时动作规格不合法。"""


@dataclass(frozen=True, slots=True)
class TimedActionSpec:
    """一个定时动作的数据规格（角色包数据）。"""

    action_key: str
    duration_frames: int
    hit_frame: int | None = None
    impact_key: str | None = None
    targeting: TargetingSpec | None = None
    transitions: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.action_key, str) or not self.action_key.strip():
            raise TimedActionSpecValidationError("action_key 必须是非空字符串")
        if isinstance(self.duration_frames, bool) or self.duration_frames <= 0:
            raise TimedActionSpecValidationError("duration_frames 必须是正整数")
        if self.hit_frame is not None and (isinstance(self.hit_frame, bool) or self.hit_frame < 0):
            raise TimedActionSpecValidationError("hit_frame 必须是非负整数")
        if self.impact_key is not None:
            if not isinstance(self.impact_key, str) or not self.impact_key.strip():
                raise TimedActionSpecValidationError("impact_key 必须是非空字符串")
            if self.hit_frame is None:
                raise TimedActionSpecValidationError(
                    f"{self.action_key} 提供 impact_key 时必须提供 hit_frame"
                )
        if self.impact_key is None and self.hit_frame is not None:
            raise TimedActionSpecValidationError(
                f"{self.action_key} 提供 hit_frame 时必须提供 impact_key"
            )
        if self.targeting is not None and not isinstance(self.targeting, TargetingSpec):
            raise TimedActionSpecValidationError("targeting 必须是 TargetingSpec 或 None")
        transitions = dict(self.transitions)
        for input_kind, frame in transitions.items():
            if not isinstance(input_kind, str) or not input_kind.strip():
                raise TimedActionSpecValidationError("transitions 键必须是非空字符串")
            if isinstance(frame, bool) or frame < 0:
                raise TimedActionSpecValidationError(f"{self.action_key} 的衔接帧不能为负数")
        object.__setattr__(self, "transitions", transitions)


def build_timed_actions(specs: Sequence[TimedActionSpec]) -> tuple[TimedImpactAction, ...]:
    """把定时动作规格统一编译为可注册的运行时动作。"""

    actions: list[TimedImpactAction] = []
    for spec in specs:
        impact_keys: tuple[str, ...] = ()
        impact_frame_offsets: dict[str, int] = {}
        if spec.impact_key is not None and spec.hit_frame is not None:
            impact_keys = (spec.impact_key,)
            impact_frame_offsets[spec.impact_key] = spec.hit_frame
        actions.append(
            TimedImpactAction(
                action_key=spec.action_key,
                duration_frames=spec.duration_frames,
                impact_keys=impact_keys,
                impact_frame_offsets=impact_frame_offsets,
                targeting=spec.targeting,
            )
        )
    return tuple(actions)
