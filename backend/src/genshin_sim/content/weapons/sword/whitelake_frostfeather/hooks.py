"""白湖冬羽被动的事件钩子。

两个钩子都只读事实，只产出下一轮结算要消费的请求：

- ``LakeLamentStackingHook``：装备者元素战技命中敌人时叠一层「湖色的哀告」。
- ``StellarEnergyRestoreHook``：装备者持有 3 层「湖色的哀告」且触发星烁反应或造成
  星烁反应伤害时，使装备者恢复元素能量。

回能的层数条件来自被动文案的结构：「持有3层时，……暴击伤害提升，且触发星烁反应
或造成星烁反应伤害时，还会使装备者恢复元素能量」——「持有3层时」是并列句的共同
状语，两项效果都受它约束。层数由目标状态只读端口回答：部分层到期不发布事实，
因此层数无法从事件流推断。

触发窗口保存为钩子实例字段（与西风系列一致）：``ContentCompiler`` 对每个宿主只
允许一个内容状态挂载，武器挂载到宿主体上会与宿主角色自身的状态段冲突；一旦引入
快照恢复或重放，窗口必须迁到内容状态挂载。

「装备者处于队伍后台时依然能触发」在判定上自然成立：两个钩子只比对归属，
不读取出战状态。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.sword.whitelake_frostfeather.data import (
    ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
    ENEMY_TARGET_PREFIX,
    ENERGY_RESTORE_INTERVAL_SECONDS,
    FRAMES_PER_SECOND,
    STACK_TRIGGER_INTERVAL_SECONDS,
    WHITELAKE_FROSTFEATHER_ATK_TERM_KEY,
    WHITELAKE_FROSTFEATHER_ENERGY_IMPACT_KEY,
)
from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_STELLAR_REACTION
from genshin_sim.core.systems.reaction import STELLAR_REACTION_KEYS

_ENERGY_RESTORE_INTERVAL_FRAMES = round(ENERGY_RESTORE_INTERVAL_SECONDS * FRAMES_PER_SECOND)
_STACK_TRIGGER_INTERVAL_FRAMES = round(STACK_TRIGGER_INTERVAL_SECONDS * FRAMES_PER_SECOND)


class LakeLamentStackingHook:
    """元素战技命中敌人时叠一层「湖色的哀告」。

    每次命中恰好追加一层；层已满时由 Buff 的 ``stack_independent`` 策略替换到期
    最早的一层，钩子不需要感知层数。
    """

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
            raise ContentUnitValidationError("湖色的哀告 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("湖色的哀告 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("湖色的哀告必须绑定正整数队伍槽位")
        if duration_frames <= 0:
            raise ContentUnitValidationError("湖色的哀告持续帧数必须为正")
        self._handler_key = handler_key
        self._owner_ref = owner_ref
        self._slot = slot
        self._atk_percent = atk_percent
        self._duration_frames = duration_frames
        self._definition_key = definition_key
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._last_proc_frame: int | None = None
        # hook_key 与 state_key 都带用途后缀：同一效果单元可以有多个钩子，
        # 共用键会让解锁条件与内容状态段相互覆盖。
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
        if not self._is_owner_result(result):
            return HookResult()
        if not self._is_elemental_skill_hit_on_enemy(result):
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            _STACK_TRIGGER_INTERVAL_FRAMES
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
                            term_key=WHITELAKE_FROSTFEATHER_ATK_TERM_KEY,
                            value=self._atk_percent,
                        ),
                    ),
                ),
            )
        )

    def _is_owner_result(self, result: object) -> bool:
        source_ref = getattr(result, "source_ref", None)
        return getattr(source_ref, "entity_id", None) == self._owner_ref

    @staticmethod
    def _is_elemental_skill_hit_on_enemy(result: object) -> bool:
        if getattr(result, "main_attack_tag", None) != ELEMENTAL_SKILL_MAIN_ATTACK_TAG:
            return False
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        return isinstance(target_id, str) and target_id.startswith(ENEMY_TARGET_PREFIX)


class StellarEnergyRestoreHook:
    """装备者持有满层「湖色的哀告」且触发星烁反应或伤害时，恢复元素能量。"""

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        slot: int,
        energy: float,
        definition_key: str,
        max_layers: int,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("星烁回能 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("星烁回能 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("星烁回能必须绑定正整数队伍槽位")
        if isinstance(max_layers, bool) or not isinstance(max_layers, int) or max_layers <= 0:
            raise ContentUnitValidationError("星烁回能层数上限必须是正整数")
        self._handler_key = handler_key
        self._owner_ref = owner_ref
        self._owner_attribute_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._energy = energy
        self._definition_key = definition_key
        self._max_layers = max_layers
        self._last_proc_frame: int | None = None
        # hook_key 与 state_key 见 LakeLamentStackingHook 的同名注释。
        self.hook_key = f"{handler_key}:{owner_ref}:energy"
        self.state_key = f"{handler_key}:energy"
        self.subscriptions = (
            "REACTION_OCCURRED",
            "DAMAGE_RESOLVED",
        )
        self.priority = 0
        self._target_status_port: TargetBuffPresenceReadPort | None = None

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def last_proc_frame(self) -> int | None:
        """最近一次成功回能的帧；仅供测试与结果投影读取。"""

        return self._last_proc_frame

    def bind_runtime_ports(
        self,
        *,
        target_status_port: TargetBuffPresenceReadPort,
    ) -> None:
        """装配期注入目标状态只读端口；未绑定时不贡献。"""

        self._target_status_port = target_status_port

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        payload = getattr(event, "payload", None)
        if payload is None:
            return HookResult()
        if not self._triggered_by_owner_stellar(payload):
            return HookResult()
        if not self._holds_full_layers(frame):
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            _ENERGY_RESTORE_INTERVAL_FRAMES
        ):
            return HookResult()
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=WHITELAKE_FROSTFEATHER_ENERGY_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    target_refs=(self._owner_ref,),
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "restore",
                            "amount": self._energy,
                            "tags": [self._handler_key],
                        }
                    },
                ),
            )
        )

    def _holds_full_layers(self, frame: int) -> bool:
        """层数条件：未绑定端口时不触发，避免装配前生效。"""

        port = self._target_status_port
        if port is None:
            return False
        return (
            port.active_stack_count(
                target_ref=self._owner_attribute_ref,
                definition_key=self._definition_key,
                frame=frame,
            )
            >= self._max_layers
        )

    def _triggered_by_owner_stellar(self, payload: object) -> bool:
        """从事件载荷判定「装备者触发星烁反应或造成星烁反应伤害」。

        - ``REACTION_OCCURRED``：读 ``occurrence.source_ref`` 的 ``source_key``，
          并校验 ``reaction_key`` 属于星烁反应集合。
        - ``DAMAGE_RESOLVED``：读 ``result.source_ref``，并校验 ``formula_key``
          为星烁完整公式，用以区分星烁与直伤。
        """

        occurrence = getattr(payload, "occurrence", None)
        if occurrence is not None:
            if occurrence.reaction_key not in STELLAR_REACTION_KEYS:
                return False
            source_ref = getattr(occurrence, "source_ref", None)
            return getattr(source_ref, "source_key", None) == self._owner_ref
        result = getattr(payload, "result", None)
        if result is None:
            return False
        if getattr(result, "formula_key", None) != FORMULA_KEY_STELLAR_REACTION:
            return False
        source_ref = getattr(result, "source_ref", None)
        return getattr(source_ref, "entity_id", None) == self._owner_ref
