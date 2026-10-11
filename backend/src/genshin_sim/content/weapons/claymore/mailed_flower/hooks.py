"""饰铁之花被动的事件钩子：元素战技命中敌人或装备者触发元素反应时刷新「风与花的密语」。"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.claymore.mailed_flower.data import (
    ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
    ENEMY_TARGET_PREFIX,
    MAILED_FLOWER_ATK_TERM_KEY,
    MAILED_FLOWER_EM_TERM_KEY,
)
from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue


class MailedFlowerWindowHook:
    """元素战技命中敌人或装备者触发元素反应时，施加「风与花的密语」。"""

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        atk_percent: float,
        elemental_mastery: float,
        duration_frames: int,
        definition_key: str,
        source_key: str,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("风与花的密语 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("风与花的密语 owner_ref 必须是非空字符串")
        if duration_frames <= 0:
            raise ContentUnitValidationError("风与花的密语持续帧数必须为正")
        self._handler_key = handler_key
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._atk_percent = atk_percent
        self._elemental_mastery = elemental_mastery
        self._duration_frames = duration_frames
        self._definition_key = definition_key
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        # hook_key 与 state_key 都带用途后缀：同一效果单元可以有多个钩子，
        # 共用键会让解锁条件与内容状态段相互覆盖。
        self.hook_key = f"{handler_key}:{owner_ref}:window"
        self.state_key = f"{handler_key}:window"
        self.subscriptions = (
            "REACTION_OCCURRED",
            "DAMAGE_RESOLVED",
        )
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
        if not self._is_owner_trigger(payload):
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
                            term_key=MAILED_FLOWER_ATK_TERM_KEY,
                            value=self._atk_percent,
                        ),
                        BuffModifierValue(
                            term_key=MAILED_FLOWER_EM_TERM_KEY,
                            value=self._elemental_mastery,
                        ),
                    ),
                ),
            )
        )

    def _is_owner_trigger(self, payload: object) -> bool:
        """判定「装备者触发元素反应」或「装备者元素战技命中敌人」。"""

        occurrence = getattr(payload, "occurrence", None)
        if occurrence is not None:
            source_key = getattr(getattr(occurrence, "source_ref", None), "source_key", None)
            return source_key == self._owner_ref
        result = getattr(payload, "result", None)
        if result is None:
            return False
        return self._is_owner_elemental_skill_hit(result)

    def _is_owner_elemental_skill_hit(self, result: object) -> bool:
        source_ref = getattr(result, "source_ref", None)
        if getattr(source_ref, "entity_id", None) != self._owner_ref:
            return False
        if getattr(result, "main_attack_tag", None) != ELEMENTAL_SKILL_MAIN_ATTACK_TAG:
            return False
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        return isinstance(target_id, str) and target_id.startswith(ENEMY_TARGET_PREFIX)
