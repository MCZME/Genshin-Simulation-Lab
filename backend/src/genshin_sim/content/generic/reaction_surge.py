"""generic 武器被动的「触发反应获得攻击力窗口」部件。

不带键：触发面（反应键集合 + 扩散方向键集合）、Buff 键与数值由各武器内容包
传入。钩子订阅 ``REACTION_OCCURRED`` 事实，只读取事实、只产出下一轮结算要
消费的 ``ApplyBuffRequest``，不直接写 Buff 状态。

「触发」判定沿用星烁回能的归属口径：``occurrence.source_ref.source_key`` 等于
装备者引用，即反应由装备者的攻击触发。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue


class ReactionSurgeHook:
    """装备者触发指定反应时，为装备者施加一个攻击力提升窗口。"""

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        slot: int,
        definition_key: str,
        term_key: str,
        atk_percent: float,
        duration_frames: int,
        source_key: str,
        reaction_keys: frozenset[str],
        swirl_reaction_key: str,
        swirl_direction_keys: frozenset[str],
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("反应窗口 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("反应窗口 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("反应窗口必须绑定正整数队伍槽位")
        if not isinstance(definition_key, str) or not definition_key.strip():
            raise ContentUnitValidationError("反应窗口 definition_key 必须是非空字符串")
        if not isinstance(term_key, str) or not term_key.strip():
            raise ContentUnitValidationError("反应窗口 term_key 必须是非空字符串")
        if isinstance(atk_percent, bool) or not isinstance(atk_percent, int | float):
            raise ContentUnitValidationError("反应窗口攻击力加成必须是数字")
        if float(atk_percent) <= 0:
            raise ContentUnitValidationError("反应窗口攻击力加成必须是正数")
        if duration_frames <= 0:
            raise ContentUnitValidationError("反应窗口持续帧数必须为正")
        if not reaction_keys and not swirl_direction_keys:
            raise ContentUnitValidationError("反应窗口触发面不能为空")
        for keys, label in (
            (reaction_keys, "反应键集合"),
            (swirl_direction_keys, "扩散方向键集合"),
        ):
            if any(not isinstance(key, str) or not key.strip() for key in keys):
                raise ContentUnitValidationError(f"反应窗口{label}必须是非空字符串")
        self._owner_ref = owner_ref
        self._slot = slot
        self._definition_key = definition_key
        self._term_key = term_key
        self._atk_percent = float(atk_percent)
        self._duration_frames = duration_frames
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._reaction_keys = frozenset(reaction_keys)
        self._swirl_reaction_key = swirl_reaction_key
        self._swirl_direction_keys = frozenset(swirl_direction_keys)
        self._owner_attribute_ref = AttributeSubjectRef.character(owner_ref)
        self.hook_key = f"{handler_key}:{owner_ref}:surge"
        self.state_key = f"{handler_key}:surge"
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
                            term_key=self._term_key,
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
        if reaction_key in self._reaction_keys:
            return True
        return (
            reaction_key == self._swirl_reaction_key
            and getattr(occurrence, "direction_key", None) in self._swirl_direction_keys
        )
