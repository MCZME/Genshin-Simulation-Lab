"""飞天大御剑被动的事件钩子：普通攻击和重击命中敌人时叠一层「勇气」。

每次命中恰好追加一层；层已满时由 Buff 的 ``stack_independent`` 策略替换到期
最早的一层，钩子不需要感知层数。触发窗口保存为钩子实例字段（与西风系列
一致）；只读取事实，只产出下一轮结算要消费的 ``ApplyBuffRequest``。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.claymore.skyrider_greatsword.data import (
    SKYRIDER_GREATSWORD_ATK_TERM_KEY,
    TRIGGER_ATTACK_TAGS,
)
from genshin_sim.core.attributes import RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue

# 敌方目标判据按 entity_id 前缀区分，与西风系列一致。
_ENEMY_TARGET_PREFIX = "target:"


class CourageStackingHook:
    """装备者普通攻击或重击命中敌人时，叠一层「勇气」。"""

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
        interval_frames: int,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("勇气 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("勇气 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("勇气必须绑定正整数队伍槽位")
        if isinstance(atk_percent, bool) or not isinstance(atk_percent, int | float):
            raise ContentUnitValidationError("勇气攻击力加成必须是数字")
        if float(atk_percent) <= 0:
            raise ContentUnitValidationError("勇气攻击力加成必须是正数")
        if duration_frames <= 0:
            raise ContentUnitValidationError("勇气持续帧数必须为正")
        if interval_frames <= 0:
            raise ContentUnitValidationError("勇气触发间隔必须为正帧数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._atk_percent = float(atk_percent)
        self._duration_frames = duration_frames
        self._definition_key = definition_key
        self._interval_frames = interval_frames
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._trigger_tags = frozenset(TRIGGER_ATTACK_TAGS)
        self._last_proc_frame: int | None = None
        self.hook_key = f"{handler_key}:{owner_ref}:layers"
        self.state_key = f"{handler_key}:layers"
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def last_proc_frame(self) -> int | None:
        """最近一次成功叠层的帧；仅供测试与结果投影读取。"""

        return self._last_proc_frame

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        source_ref = getattr(result, "source_ref", None)
        if getattr(source_ref, "entity_id", None) != self._owner_ref:
            return HookResult()
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        if not isinstance(target_id, str) or not target_id.startswith(_ENEMY_TARGET_PREFIX):
            return HookResult()
        if getattr(result, "main_attack_tag", None) not in self._trigger_tags:
            return HookResult()
        if not self._dealt_damage(result):
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            self._interval_frames
        ):
            return HookResult()
        self._last_proc_frame = frame
        return HookResult(
            buff_requests=(
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{frame}",
                    frame=frame,
                    order=0,
                    definition_key=self._definition_key,
                    target_ref=result.source_ref,
                    source_context=self._source_context,
                    duration_frames=self._duration_frames,
                    applier_ref=result.source_ref,
                    modifier_values=(
                        BuffModifierValue(
                            term_key=SKYRIDER_GREATSWORD_ATK_TERM_KEY,
                            value=self._atk_percent,
                        ),
                    ),
                ),
            )
        )

    @staticmethod
    def _dealt_damage(result: object) -> bool:
        damage = getattr(result, "final_damage", None)
        if isinstance(damage, bool) or not isinstance(damage, int | float):
            return False
        return damage > 0
