"""铁影阔剑被动的事件钩子：生命值低于 70% 期间维持「不屈」标记。

Buff 条件是连续状态（生命比例低于阈值），事件流无法表达「条件持续成立」，
因此由 ``FRAME_STARTED`` 合成 tick 周期性重评：条件成立时周期性重新施加
（refresh 策略续期），条件失效后不再施加、标记自然到期。

工程近似（文档义务）：条件每 10 帧重评一次，条件失效后的残留时长至多一个
标记持续期（20 帧）。游戏内条件失效时标记立即消失；本实现的残留窗口是当前
事件流能力下的工程约定，不作为游戏真值。生命读取走
``simulation.get_system(HealthRuntime)`` 只读端口（与角色内容侧先例一致），
钩子自身不写任何状态。
"""

from __future__ import annotations

from typing import Any

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff import ApplyBuffRequest
from genshin_sim.core.systems.health import HealthRuntime


class UnyieldingMarkerHook:
    """生命比例低于阈值期间，为装备者维持「不屈」标记。"""

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
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("不屈标记 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("不屈标记 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("不屈标记必须绑定正整数队伍槽位")
        if not isinstance(definition_key, str) or not definition_key.strip():
            raise ContentUnitValidationError("不屈标记 definition_key 必须是非空字符串")
        if duration_frames <= 0:
            raise ContentUnitValidationError("不屈标记持续帧数必须为正")
        if refresh_interval_frames <= 0:
            raise ContentUnitValidationError("不屈标记重评间隔必须为正")
        if duration_frames < refresh_interval_frames:
            raise ContentUnitValidationError(
                "不屈标记持续期不得短于重评间隔，否则条件成立期间会出现无标记空档"
            )
        if not 0.0 < threshold < 1.0:
            raise ContentUnitValidationError("不屈标记阈值必须在 0 到 1 之间")
        self._owner_ref = owner_ref
        self._definition_key = definition_key
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._duration_frames = duration_frames
        self._refresh_interval_frames = refresh_interval_frames
        self._threshold = float(threshold)
        self._owner_attribute_ref = AttributeSubjectRef.character(owner_ref)
        self._last_apply_frame: int | None = None
        self.hook_key = f"{handler_key}:{owner_ref}:marker"
        self.state_key = f"{handler_key}:marker"
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
        if health.get_hp_ratio(self._owner_attribute_ref, frame) >= self._threshold:
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
                ),
            )
        )


def _health_runtime(context: object) -> HealthRuntime | None:
    simulation: Any = (
        context if hasattr(context, "get_system") else getattr(context, "simulation", None)
    )
    if simulation is None:
        return None
    health = simulation.get_system(HealthRuntime)
    return health if isinstance(health, HealthRuntime) else None
