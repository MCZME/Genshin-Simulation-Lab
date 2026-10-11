"""讨龙英杰谭被动的事件钩子：主动切换角色时，为新登场角色施加「传承」。

订阅 ``TEAM_SWITCHED`` 事实（accepted 的切换），把攻击力 Buff 施加到切换后的
当前场上角色；触发不要求穿戴者在场，间隔窗口保存为钩子实例字段（与西风系列
一致）。只读取事实，只产出下一轮结算要消费的 ``ApplyBuffRequest``。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.catalyst.thrilling_tales_of_dragon_slayers.data import (
    THRILLING_TALES_ATK_TERM_KEY,
)
from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue


class LegacySwitchHook:
    """切换角色时，为新登场的角色施加「传承」攻击力窗口。"""

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        slot: int,
        atk_percent: float,
        duration_frames: int,
        interval_frames: int,
        definition_key: str,
        source_key: str,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("传承 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("传承 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("传承必须绑定正整数队伍槽位")
        if isinstance(atk_percent, bool) or not isinstance(atk_percent, int | float):
            raise ContentUnitValidationError("传承攻击力加成必须是数字")
        if float(atk_percent) <= 0:
            raise ContentUnitValidationError("传承攻击力加成必须是正数")
        if duration_frames <= 0:
            raise ContentUnitValidationError("传承持续帧数必须为正")
        if interval_frames <= 0:
            raise ContentUnitValidationError("传承触发间隔必须为正帧数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._atk_percent = float(atk_percent)
        self._duration_frames = duration_frames
        self._interval_frames = interval_frames
        self._definition_key = definition_key
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._last_proc_frame: int | None = None
        self.hook_key = f"{handler_key}:{owner_ref}:legacy"
        self.state_key = f"{handler_key}:legacy"
        self.subscriptions = ("TEAM_SWITCHED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def last_proc_frame(self) -> int | None:
        """最近一次成功触发的帧；仅供测试与结果投影读取。"""

        return self._last_proc_frame

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        payload = getattr(event, "payload", None)
        if payload is None:
            return HookResult()
        if not getattr(payload, "accepted", False):
            return HookResult()
        active_slot = getattr(payload, "active_slot", None)
        if isinstance(active_slot, bool) or not isinstance(active_slot, int) or active_slot <= 0:
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            self._interval_frames
        ):
            return HookResult()
        self._last_proc_frame = frame
        target_ref = AttributeSubjectRef.character(f"character:slot_{active_slot}")
        return HookResult(
            buff_requests=(
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{frame}",
                    frame=frame,
                    order=0,
                    definition_key=self._definition_key,
                    target_ref=target_ref,
                    source_context=self._source_context,
                    duration_frames=self._duration_frames,
                    modifier_values=(
                        BuffModifierValue(
                            term_key=THRILLING_TALES_ATK_TERM_KEY,
                            value=self._atk_percent,
                        ),
                    ),
                ),
            )
        )
