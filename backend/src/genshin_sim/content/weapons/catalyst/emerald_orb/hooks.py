"""翡玉法球被动的事件钩子：触发水系反应（含水扩散）时获得「激流」攻击力窗口。

订阅 ``REACTION_OCCURRED`` 事实，只读取事实、只产出下一轮结算要消费的
``ApplyBuffRequest``，不直接写 Buff 状态。「触发」判定沿用星烁回能的归属口径：
``occurrence.source_ref.source_key`` 等于装备者引用，即反应由装备者的攻击触发。
窗口可叠加触发（refresh 策略续期），钩子不感知层数。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.catalyst.emerald_orb.data import (
    EMERALD_ORB_ATK_TERM_KEY,
    SWIRL_DIRECTION_KEYS,
    SWIRL_REACTION_KEY_DECLARED,
    TRIGGER_REACTION_KEYS,
)
from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue


class RiptideReactionHook:
    """装备者触发指定反应时，为装备者施加「激流」攻击力窗口。"""

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
            raise ContentUnitValidationError("激流 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("激流 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("激流必须绑定正整数队伍槽位")
        if isinstance(atk_percent, bool) or not isinstance(atk_percent, int | float):
            raise ContentUnitValidationError("激流攻击力加成必须是数字")
        if float(atk_percent) <= 0:
            raise ContentUnitValidationError("激流攻击力加成必须是正数")
        if duration_frames <= 0:
            raise ContentUnitValidationError("激流持续帧数必须为正")
        self._owner_ref = owner_ref
        self._atk_percent = float(atk_percent)
        self._duration_frames = duration_frames
        self._definition_key = definition_key
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._owner_attribute_ref = AttributeSubjectRef.character(owner_ref)
        self.hook_key = f"{handler_key}:{owner_ref}:riptide"
        self.state_key = f"{handler_key}:riptide"
        self.subscriptions = ("REACTION_OCCURRED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        occurrence = getattr(getattr(event, "payload", None), "occurrence", None)
        if occurrence is None:
            return HookResult()
        source_ref = getattr(occurrence, "source_ref", None)
        if getattr(source_ref, "source_key", None) != self._owner_ref:
            return HookResult()
        if not self._reaction_matches(occurrence):
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
                            term_key=EMERALD_ORB_ATK_TERM_KEY,
                            value=self._atk_percent,
                        ),
                    ),
                ),
            )
        )

    def _reaction_matches(self, occurrence: object) -> bool:
        reaction_key = getattr(occurrence, "reaction_key", None)
        if not isinstance(reaction_key, str):
            return False
        if reaction_key in TRIGGER_REACTION_KEYS:
            return True
        return (
            reaction_key == SWIRL_REACTION_KEY_DECLARED
            and getattr(occurrence, "direction_key", None) in SWIRL_DIRECTION_KEYS
        )
