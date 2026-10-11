"""generic 武器被动的「生命阈值门控 Buff 维持」部件。

不带键：阈值方向、Buff 键与词条由各武器内容包传入。装备者的 Buff 条件是
连续状态（生命比例高于/低于阈值），事件流无法表达「条件持续成立」，因此由
``FRAME_STARTED`` 合成 tick 周期性重评：条件成立时周期性重新施加（refresh
策略续期），条件失效后不再施加、Buff 自然到期。

工程近似（文档义务）：条件重评间隔 ``refresh_interval_frames``，条件失效后的
残留时长至多一个 Buff 持续期（``duration_frames``）。游戏内条件失效时 Buff
立即消失；本部件的残留窗口是当前事件流能力下的工程约定，不作为游戏真值。
生命读取走 ``simulation.get_system(HealthRuntime)`` 只读端口（与角色内容侧
先例一致），钩子自身不写任何状态。
"""

from __future__ import annotations

from typing import Any

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue
from genshin_sim.core.systems.health import HealthRuntime


class HpGatedBuffHook:
    """生命比例满足阈值期间，为装备者维持一个 Buff。"""

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        slot: int,
        definition_key: str,
        source_key: str,
        duration_frames: int,
        refresh_interval_frames: int,
        threshold: float,
        direction: str,
        modifier_values: tuple[BuffModifierValue, ...] = (),
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("生命门控 Buff handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("生命门控 Buff owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("生命门控 Buff 必须绑定正整数队伍槽位")
        if not isinstance(definition_key, str) or not definition_key.strip():
            raise ContentUnitValidationError("生命门控 Buff definition_key 必须是非空字符串")
        if isinstance(duration_frames, bool) or not isinstance(duration_frames, int):
            raise ContentUnitValidationError("生命门控 Buff 持续帧数必须是整数")
        if duration_frames <= 0:
            raise ContentUnitValidationError("生命门控 Buff 持续帧数必须为正")
        if isinstance(refresh_interval_frames, bool) or not isinstance(
            refresh_interval_frames, int
        ):
            raise ContentUnitValidationError("生命门控 Buff 重评间隔必须是整数")
        if refresh_interval_frames <= 0:
            raise ContentUnitValidationError("生命门控 Buff 重评间隔必须为正")
        if duration_frames < refresh_interval_frames:
            raise ContentUnitValidationError(
                "生命门控 Buff 持续期不得短于重评间隔，否则条件成立期间会出现无 Buff 空档"
            )
        if isinstance(threshold, bool) or not isinstance(threshold, int | float):
            raise ContentUnitValidationError("生命门控 Buff 阈值必须是数字")
        if not 0.0 < float(threshold) < 1.0:
            raise ContentUnitValidationError("生命门控 Buff 阈值必须在 0 到 1 之间")
        if direction not in {"above", "below"}:
            raise ContentUnitValidationError("生命门控 Buff 方向只支持 above 或 below")
        self._owner_ref = owner_ref
        self._slot = slot
        self._definition_key = definition_key
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._duration_frames = duration_frames
        self._refresh_interval_frames = refresh_interval_frames
        self._threshold = float(threshold)
        self._direction = direction
        self._modifier_values = tuple(modifier_values)
        self._owner_attribute_ref = AttributeSubjectRef.character(owner_ref)
        self._last_apply_frame: int | None = None
        self.hook_key = f"{handler_key}:{owner_ref}:hp_gate"
        self.state_key = f"{handler_key}:hp_gate"
        self.subscriptions = ("FRAME_STARTED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def last_apply_frame(self) -> int | None:
        """最近一次续期的帧；仅供测试与结果投影读取。"""

        return self._last_apply_frame

    def handle(self, event: object, context: object) -> HookResult:
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame <= 0:
            return HookResult()
        if self._last_apply_frame is not None and frame - self._last_apply_frame < (
            self._refresh_interval_frames
        ):
            return HookResult()
        health = _health_runtime(context)
        if health is None:
            return HookResult()
        ratio = health.get_hp_ratio(self._owner_attribute_ref, frame)
        if not self._condition_holds(ratio):
            return HookResult()
        self._last_apply_frame = frame
        return HookResult(
            buff_requests=(
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{frame}",
                    frame=frame,
                    order=0,
                    definition_key=self._definition_key,
                    target_ref=self._owner_attribute_ref,
                    source_context=self._source_context,
                    duration_frames=self._duration_frames,
                    applier_ref=self._owner_attribute_ref,
                    modifier_values=self._modifier_values,
                ),
            )
        )

    def _condition_holds(self, ratio: float) -> bool:
        if self._direction == "above":
            return ratio > self._threshold
        return ratio < self._threshold


def _health_runtime(context: object) -> HealthRuntime | None:
    simulation: Any = (
        context if hasattr(context, "get_system") else getattr(context, "simulation", None)
    )
    if simulation is None:
        return None
    health = simulation.get_system(HealthRuntime)
    return health if isinstance(health, HealthRuntime) else None
