"""飞天御剑被动的事件钩子：装备者施放元素爆发时获得「决心」攻击力窗口。

订阅 ``ACTION_STARTED`` 事实（触发面与圣遗物同源：``owner_slot`` 命中穿戴者、
``ability_key`` 为元素爆发）；只读取事实，只产出下一轮结算要消费的
``ApplyBuffRequest``。窗口可叠加触发（refresh 策略续期），钩子不感知层数。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.sword.skyrider_sword.data import (
    SKYRIDER_SWORD_ATK_TERM_KEY,
    TRIGGER_ABILITY_KEY,
)
from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue


class ResolveCastHook:
    """装备者施放元素爆发时，为装备者施加「决心」攻击力窗口。"""

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        slot: int,
        atk_percent: float,
        duration_frames: int,
        definition_key: str,
        source_key: str,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("决心 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("决心 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("决心必须绑定正整数队伍槽位")
        if isinstance(atk_percent, bool) or not isinstance(atk_percent, int | float):
            raise ContentUnitValidationError("决心攻击力加成必须是数字")
        if float(atk_percent) <= 0:
            raise ContentUnitValidationError("决心攻击力加成必须是正数")
        if duration_frames <= 0:
            raise ContentUnitValidationError("决心持续帧数必须为正")
        self._owner_ref = owner_ref
        self._slot = slot
        self._atk_percent = float(atk_percent)
        self._duration_frames = duration_frames
        self._definition_key = definition_key
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._owner_attribute_ref = AttributeSubjectRef.character(owner_ref)
        self.hook_key = f"{handler_key}:{owner_ref}:resolve"
        self.state_key = f"{handler_key}:resolve"
        self.subscriptions = ("ACTION_STARTED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        payload = getattr(event, "payload", None)
        if payload is None:
            return HookResult()
        if getattr(payload, "owner_slot", None) != self._slot:
            return HookResult()
        if getattr(payload, "ability_key", None) != TRIGGER_ABILITY_KEY:
            return HookResult()
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
                    modifier_values=(
                        BuffModifierValue(
                            term_key=SKYRIDER_SWORD_ATK_TERM_KEY,
                            value=self._atk_percent,
                        ),
                    ),
                ),
            )
        )
