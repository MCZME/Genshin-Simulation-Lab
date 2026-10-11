"""浪影阔剑被动的事件钩子：装备者受到治疗后刷新「巡航的白浪」。"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.claymore.tidal_shadow.data import (
    TIDAL_SHADOW_ATK_TERM_KEY,
)
from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue


class TidalShadowHealingHook:
    """装备者受到治疗后，向装备者施加「巡航的白浪」攻击力 Buff。"""

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        atk_percent: float,
        duration_frames: int,
        definition_key: str,
        source_key: str,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("巡航的白浪 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("巡航的白浪 owner_ref 必须是非空字符串")
        if duration_frames <= 0:
            raise ContentUnitValidationError("巡航的白浪持续帧数必须为正")
        self._handler_key = handler_key
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._atk_percent = atk_percent
        self._duration_frames = duration_frames
        self._definition_key = definition_key
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        # hook_key 与 state_key 都带用途后缀：同一效果单元可以有多个钩子，
        # 共用键会让解锁条件与内容状态段相互覆盖。
        self.hook_key = f"{handler_key}:{owner_ref}:healing"
        self.state_key = f"{handler_key}:healing"
        self.subscriptions = ("HEALING_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        target_ref = getattr(result, "target_ref", None)
        if getattr(target_ref, "entity_id", None) != self._owner_ref:
            return HookResult()
        return HookResult(
            buff_requests=(
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{frame}",
                    frame=frame,
                    order=0,
                    definition_key=self._definition_key,
                    target_ref=self._owner_subject_ref,
                    source_context=self._source_context,
                    duration_frames=self._duration_frames,
                    applier_ref=self._owner_subject_ref,
                    modifier_values=(
                        BuffModifierValue(
                            term_key=TIDAL_SHADOW_ATK_TERM_KEY,
                            value=self._atk_percent,
                        ),
                    ),
                ),
            )
        )
