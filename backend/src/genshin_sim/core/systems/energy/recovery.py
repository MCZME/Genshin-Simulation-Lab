"""通用能量恢复机制：普攻/重击标签伤害的概率回能判定。

判定由伤害结算事实驱动：事实响应组件只读取已发布的 ``DAMAGE_RESOLVED`` 事实，
不同步写能量，恢复经统一意图队列产出下一轮结算消费的直接恢复请求。
规则数值、触发词表与稳定 key 以元素能量系统契约为准。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
)
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.events import EventType
from genshin_sim.core.simulation.random_source import RandomSource
from genshin_sim.core.systems.energy.errors import (
    CharacterEnergyNotFoundError,
    EnergyRecoveryError,
    EnergyValidationError,
)
from genshin_sim.core.systems.energy.models import validate_character_ref
from genshin_sim.core.systems.energy.store import CharacterEnergyStore

if TYPE_CHECKING:
    from genshin_sim.core.simulation.intent_queue import IntentQueue
    from genshin_sim.core.systems.energy.runtime import TeamReadPort

# 恢复量固定为 1 点能量（直接恢复，不经载体与充能效率公式）。
ENERGY_RECOVERY_RESTORE_AMOUNT = 1.0

# 恢复请求与变化审计使用的稳定 key 与附加标签。
ENERGY_RECOVERY_IMPACT_KEY = "energy.recovery.restore"
ENERGY_RECOVERY_SOURCE_TAG = "energy.recovery"

# 触发标签词表（内容命名约定，见模块 docstring）。
NORMAL_ATTACK_TAG_PREFIX = "普通攻击"
CHARGED_ATTACK_TAG = "重击"


@dataclass(frozen=True, slots=True)
class EnergyRecoveryRule:
    """一种武器类型的通用回能判定参数。"""

    initial_probability: float
    failure_increment: float

    def __post_init__(self) -> None:
        for name, value in (
            ("initial_probability", self.initial_probability),
            ("failure_increment", self.failure_increment),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise EnergyValidationError(f"{name} 必须是数字")
            if not math.isfinite(float(value)):
                raise EnergyValidationError(f"{name} 必须是有限数字")
        if not 0.0 <= self.initial_probability <= 1.0:
            raise EnergyValidationError("initial_probability 必须在 0 到 1 之间")
        if not 0.0 <= self.failure_increment <= 1.0:
            raise EnergyValidationError("failure_increment 必须在 0 到 1 之间")


# 按武器类型的初始概率与失败递增。
ENERGY_RECOVERY_RULES_BY_WEAPON_TYPE: Mapping[str, EnergyRecoveryRule] = {
    "sword": EnergyRecoveryRule(0.10, 0.05),
    "claymore": EnergyRecoveryRule(0.00, 0.10),
    "polearm": EnergyRecoveryRule(0.00, 0.04),
    "catalyst": EnergyRecoveryRule(0.00, 0.10),
    "bow": EnergyRecoveryRule(0.00, 0.05),
}


def recovery_rule_for_weapon_type(weapon_type: str) -> EnergyRecoveryRule:
    """按资产武器类型取回能判定规则；未知类型在组装阶段失败。"""

    if not isinstance(weapon_type, str) or not weapon_type.strip():
        raise EnergyValidationError("武器类型必须是非空字符串")
    rule = ENERGY_RECOVERY_RULES_BY_WEAPON_TYPE.get(weapon_type)
    if rule is None:
        raise EnergyValidationError(f"未知武器类型的通用回能规则：{weapon_type!r}")
    return rule


def is_energy_recovery_trigger_tag(tag: object) -> bool:
    """判断伤害主攻击标签是否触发通用回能判定。"""

    if not isinstance(tag, str) or not tag:
        return False
    return tag == CHARGED_ATTACK_TAG or tag.startswith(NORMAL_ATTACK_TAG_PREFIX)


class EnergyRecoveryStore:
    """角色通用回能判定概率状态的唯一索引。

    每个角色保存“下一次判定的触发概率”，初始值取武器类型规则的
    ``initial_probability``；判定成功重置回初始值，失败累加
    ``failure_increment`` 并封顶 1.0。状态跨切人保留。
    """

    __slots__ = ("_entries",)

    def __init__(
        self,
        entries: Iterable[tuple[AttributeSubjectRef, EnergyRecoveryRule]],
    ) -> None:
        result: dict[AttributeSubjectRef, tuple[EnergyRecoveryRule, float]] = {}
        for character_ref, rule in entries:
            validate_character_ref(character_ref)
            if not isinstance(rule, EnergyRecoveryRule):
                raise EnergyValidationError("通用回能规则必须是 EnergyRecoveryRule")
            if character_ref in result:
                raise EnergyValidationError(f"角色通用回能主体重复：{character_ref.entity_id}")
            result[character_ref] = (rule, rule.initial_probability)
        self._entries = result

    def contains(self, character_ref: AttributeSubjectRef) -> bool:
        validate_character_ref(character_ref)
        return character_ref in self._entries

    def next_probability(self, character_ref: AttributeSubjectRef) -> float:
        return self._require(character_ref)[1]

    def record_success(self, character_ref: AttributeSubjectRef) -> None:
        rule, _ = self._require(character_ref)
        self._entries[character_ref] = (rule, rule.initial_probability)

    def record_failure(self, character_ref: AttributeSubjectRef) -> None:
        rule, probability = self._require(character_ref)
        self._entries[character_ref] = (rule, min(probability + rule.failure_increment, 1.0))

    def _require(self, character_ref: AttributeSubjectRef) -> tuple[EnergyRecoveryRule, float]:
        validate_character_ref(character_ref)
        entry = self._entries.get(character_ref)
        if entry is None:
            raise CharacterEnergyNotFoundError(
                f"角色通用回能判定状态不存在：{character_ref.entity_id}"
            )
        return entry


class EnergyRecoveryStage:
    """事实响应阶段组件：消费伤害结算事实并执行通用回能判定。

    按帧游标消费 ``DAMAGE_RESOLVED`` 事实（与共鸣响应阶段一致）：命中触发
    标签、且来源角色在场、且使用标准能量资源时进行一次概率判定。概率状态
    就地提交；判定成功经统一意图队列产出下一轮结算消费的能量恢复请求，
    不在事实处理中同步写入能量领域。
    """

    def __init__(
        self,
        recovery_store: EnergyRecoveryStore,
        energy_store: CharacterEnergyStore,
        team_state: TeamReadPort,
        intent_queue: IntentQueue,
    ) -> None:
        self._recovery_store = recovery_store
        self._energy_store = energy_store
        self._team_state = team_state
        self._intent_queue = intent_queue
        self._slot_by_entity_id = {
            character.combat_entity_id: character.slot for character in team_state.characters
        }
        self._processed_frame = -1
        self._processed_count = 0

    def update_frame(self, context, frame: int) -> None:
        if self._processed_frame != frame:
            self._processed_frame = frame
            self._processed_count = 0
        events = context.events.frame_events
        for event_index in range(self._processed_count, len(events)):
            self._processed_count += 1
            event = events[event_index]
            if event.event_type is EventType.DAMAGE_RESOLVED:
                result = getattr(event.payload, "result", None)
                if result is not None:
                    self._judge(context, result, frame, event_index)

    def is_idle(self) -> bool:
        return True

    def _judge(self, context, result, frame: int, event_index: int) -> None:
        source_ref = getattr(result, "source_ref", None)
        if not isinstance(source_ref, AttributeSubjectRef):
            return
        if source_ref.kind is not AttributeSubjectKind.CHARACTER:
            return
        if not self._recovery_store.contains(source_ref):
            return
        if not is_energy_recovery_trigger_tag(getattr(result, "main_attack_tag", None)):
            return
        slot = self._slot_by_entity_id.get(source_ref.entity_id)
        if slot is None or slot != self._team_state.active_slot:
            # 后台不判定：不消耗随机序列，也不累积概率。
            return
        if self._energy_store.require_profile(source_ref).capacity <= 0.0:
            return
        random_source = getattr(context, "random_source", None)
        if not isinstance(random_source, RandomSource):
            raise EnergyRecoveryError(
                f"通用回能判定缺少装配期注入的仿真随机源：{source_ref.entity_id}"
            )
        if random_source.roll(self._recovery_store.next_probability(source_ref)):
            self._recovery_store.record_success(source_ref)
            self._enqueue_restore(context, result, source_ref, slot, frame, event_index)
        else:
            self._recovery_store.record_failure(source_ref)

    def _enqueue_restore(
        self,
        context,
        result,
        source_ref: AttributeSubjectRef,
        slot: int,
        frame: int,
        event_index: int,
    ) -> None:
        # 延迟导入：core.impacts.runtime 反向依赖本领域包，模块级导入成环。
        from genshin_sim.core.impacts import ImpactKind, ImpactRequest

        request_id = (
            f"energy.recovery:{getattr(result, 'request_id', 'damage')}:{frame}:{event_index}"
        )
        request = ImpactRequest(
            frame=frame,
            kind=ImpactKind.ENERGY,
            impact_key=ENERGY_RECOVERY_IMPACT_KEY,
            owner_slot=slot,
            request_id=request_id,
            target_refs=(source_ref.entity_id,),
            tags=(ENERGY_RECOVERY_SOURCE_TAG,),
            params={
                "energy": {
                    "schema_version": 1,
                    "operation": "restore",
                    "amount": ENERGY_RECOVERY_RESTORE_AMOUNT,
                    "tags": [ENERGY_RECOVERY_SOURCE_TAG],
                }
            },
        )
        self._intent_queue.enqueue(
            IntentEnvelope(
                intent_id=request_id,
                kind=IntentKind.IMPACT,
                frame=context.current_frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=ENERGY_RECOVERY_SOURCE_TAG,
                payload=request,
            )
        )
