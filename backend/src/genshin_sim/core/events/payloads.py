from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from genshin_sim.core.attributes.panel import AttributePanelChange
    from genshin_sim.core.coordination.character_damage_taken.models import (
        CharacterDamageTakenRecord,
    )
    from genshin_sim.core.coordination.elemental_reaction.models import (
        ElementalInteractionBatchRecord,
    )
    from genshin_sim.core.space.entities import SpatialEntity
    from genshin_sim.core.systems.aura.models import (
        AuraApplicationResult,
        AuraTransitionResult,
    )
    from genshin_sim.core.systems.aura_icd.models import IcdResolution
    from genshin_sim.core.systems.buff.models import (
        BuffApplicationResult,
        BuffRemovalResult,
    )
    from genshin_sim.core.systems.damage.models import DamageResult
    from genshin_sim.core.systems.energy.models import (
        CharacterEnergyChangeResult,
        EnergyPickupRecord,
        EnergyPickupSettlementResult,
    )
    from genshin_sim.core.systems.healing.models import HealingResult
    from genshin_sim.core.systems.health.models import (
        CharacterHealthChangeResult,
        CharacterMaxHpReconcileResult,
    )
    from genshin_sim.core.systems.infusion.models import (
        InfusionApplicationResult,
        InfusionRemovalResult,
    )
    from genshin_sim.core.systems.reaction.models import (
        CapturedCrystallizeShieldBasis,
        CapturedTransformativeScalingBasis,
        DynamicTransformativeScalingBasis,
        ReactionOccurrence,
    )
    from genshin_sim.core.systems.reaction.states import (
        ReactionStateChange,
        ReactionStateRecord,
    )
    from genshin_sim.core.systems.shield.models import (
        ShieldAbsorptionResult,
        ShieldCapacityChangeResult,
        ShieldGrantResult,
        ShieldRemovalResult,
    )


class EventPayload(Protocol):
    """事件载荷协议。"""

    def to_dict(self) -> dict[str, object]:
        """转换为可序列化字典。"""
        ...


class _ElementalStateLinkLike(Protocol):
    link_key: str


class _FrozenStateLike(Protocol):
    state_link_ref: _ElementalStateLinkLike
    created_frame: int


@dataclass(frozen=True, slots=True)
class EmptyPayload:
    """无字段事件载荷。"""

    def to_dict(self) -> dict[str, object]:
        return {}


@dataclass(frozen=True, slots=True)
class SimulationEndedPayload:
    """仿真结束事件载荷。"""

    stop_reason: str
    end_frame: int
    frames_run: int

    def to_dict(self) -> dict[str, object]:
        return {
            "stop_reason": self.stop_reason,
            "end_frame": self.end_frame,
            "frames_run": self.frames_run,
        }


@dataclass(frozen=True, slots=True)
class InputKeyReceivedPayload:
    """输入按键事实进入运行时处理的事件载荷。"""

    key: str
    phase: str
    order: int
    session_id: int

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "phase": self.phase,
            "order": self.order,
            "session_id": self.session_id,
        }


@dataclass(frozen=True, slots=True)
class InputSessionBoundaryPayload:
    """输入会话边界被 ActionManager 处理的事件载荷。"""

    session_id: int
    key: str
    phase: str
    order: int
    press_frame: int
    held_frames: int
    physical_state: str
    control_state: str
    owner_kind: str
    owner_slot: int | None
    interpreter_id: str
    binding_scope: str
    will_interpret: bool
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "key": self.key,
            "phase": self.phase,
            "order": self.order,
            "press_frame": self.press_frame,
            "held_frames": self.held_frames,
            "physical_state": self.physical_state,
            "control_state": self.control_state,
            "owner_kind": self.owner_kind,
            "owner_slot": self.owner_slot,
            "interpreter_id": self.interpreter_id,
            "binding_scope": self.binding_scope,
            "will_interpret": self.will_interpret,
            "skip_reason": self.skip_reason,
        }


@dataclass(frozen=True, slots=True)
class DamageResolvedPayload:
    """一次伤害数值已经完成结算的事实载荷。"""

    result: DamageResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class HealingResolvedPayload:
    """一次理论治疗量已经完成结算的事实载荷。"""

    result: HealingResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class CharacterHealthChangedPayload:
    """一次角色当前生命值已经提交变化的状态载荷。"""

    result: CharacterHealthChangeResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class CharacterMaxHpChangedPayload:
    """一次角色最大生命同步造成当前生命同比调整的审计载荷。"""

    result: CharacterMaxHpReconcileResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class EnergyPickupSpawnedPayload:
    """元素微粒或晶球已进入在途队列。"""

    record: EnergyPickupRecord

    def to_dict(self) -> dict[str, object]:
        return {"record": self.record.to_dict()}


@dataclass(frozen=True, slots=True)
class EnergyPickupSettledPayload:
    """元素微粒或晶球已向整个队伍完成结算。"""

    result: EnergyPickupSettlementResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class DirectEnergyChangeResolvedPayload:
    """直接恢复、直接扣除或爆发扣能已提交。"""

    result: CharacterEnergyChangeResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class CharacterEnergyChangedPayload:
    """角色当前元素能量实际发生变化。"""

    result: CharacterEnergyChangeResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class ShieldGrantedPayload:
    """护盾实例已经创建、替换或刷新的状态载荷。"""

    result: ShieldGrantResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class ShieldCapacityChangedPayload:
    """护盾原生剩余量已经变化的状态载荷。"""

    result: ShieldCapacityChangeResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class ShieldRemovedPayload:
    """护盾实例已经离开活动状态的状态载荷。"""

    result: ShieldRemovalResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class ShieldAbsorptionResolvedPayload:
    """一次并行护盾吸收已经提交完成的事实载荷。"""

    result: ShieldAbsorptionResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class DamageAppliedPayload:
    """一份正伤害已经以角色为应用目标的事实载荷。"""

    record: CharacterDamageTakenRecord

    def to_dict(self) -> dict[str, object]:
        return {"record": self.record.to_dict()}


@dataclass(frozen=True, slots=True)
class BuffAppliedPayload:
    """Buff 实例已经创建、刷新、替换或叠层的状态载荷。"""

    result: BuffApplicationResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class BuffRemovedPayload:
    """Buff 实例已经离开活动状态的状态载荷。"""

    result: BuffRemovalResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class InfusionAppliedPayload:
    """附魔/转化来源已创建、替换或刷新的状态载荷。"""

    result: InfusionApplicationResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class InfusionRemovedPayload:
    """附魔/转化来源已离开活动状态的状态载荷。"""

    result: InfusionRemovalResult

    def to_dict(self) -> dict[str, object]:
        return {"result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class AuraIcdResolvedPayload:
    """元素附着 ICD 已提交本次命中系数的事实载荷。"""

    result: IcdResolution

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.result.request_id,
            "impact_ref": self.result.impact_ref,
            "order": self.result.order,
            "outcome": self.result.outcome.value,
            "coefficient": self.result.coefficient.to_dict(),
            "allows_application": self.result.allows_application,
            "tag_key": self.result.tag_key,
            "sequence_key": self.result.sequence_key,
            "attacker_ref": self.result.attacker_ref.to_dict(),
            "defender_ref": self.result.defender_ref.to_dict(),
            "before": None if self.result.before is None else self.result.before.to_dict(),
            "after": None if self.result.after is None else self.result.after.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class AuraAppliedPayload:
    """普通附着或同元素叠加已提交的事实载荷。"""

    result: AuraApplicationResult

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.result.request_id,
            "application_id": self.result.application_id,
            "subject_ref": self.result.subject_ref.entity_id,
            "aura_kind": self.result.aura_kind.value,
            "outcome": self.result.outcome.value,
            "before": None if self.result.before is None else self.result.before.to_dict(),
            "after": None if self.result.after is None else self.result.after.to_dict(),
            "amount_after": None
            if self.result.after is None
            else self.result.after.current_amount.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class MovementCollidedPayload:
    """下坠碰撞事实载荷。"""

    entity_id: str
    frame: int

    def to_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "frame": self.frame,
        }


@dataclass(frozen=True, slots=True)
class MovementLandedPayload:
    """落地事实载荷。"""

    entity_id: str
    frame: int
    fall_start_frame: int
    fall_height: float

    def to_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "frame": self.frame,
            "fall_start_frame": self.fall_start_frame,
            "fall_height": self.fall_height,
        }


@dataclass(frozen=True, slots=True)
class ResonanceActivatedPayload:
    """元素共鸣激活集合已确定的一次性事实载荷。"""

    active_keys: tuple[str, ...]
    team_size: int
    established_frame: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "active_keys": tuple(self.active_keys),
            "team_size": self.team_size,
            "established_frame": self.established_frame,
        }


@dataclass(frozen=True, slots=True)
class ActionStartedPayload:
    """一次动作实例已经开始运行的事实载荷。"""

    instance_id: int
    frame: int
    action_key: str
    owner_slot: int | None = None
    ability_key: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_id": self.instance_id,
            "frame": self.frame,
            "action_key": self.action_key,
            "owner_slot": self.owner_slot,
            "ability_key": self.ability_key,
        }


@dataclass(frozen=True, slots=True)
class MoonsignLevelSetPayload:
    """月兆等级与月兆角色集合已确定的事实载荷。"""

    level: str
    moonsign_character_refs: tuple[str, ...]
    established_frame: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "moonsign_character_refs": tuple(self.moonsign_character_refs),
            "established_frame": self.established_frame,
        }


@dataclass(frozen=True, slots=True)
class MoonsignBonusAppliedPayload:
    """非月兆角色施放 E/Q 后覆盖式应用的月曜增伤事实载荷。"""

    frame: int
    source_ref: str
    value: float
    expires_at_frame: int

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "source_ref": self.source_ref,
            "value": self.value,
            "expires_at_frame": self.expires_at_frame,
        }


@dataclass(frozen=True, slots=True)
class MoonsignBonusExpiredPayload:
    """非月兆月曜增伤到期清除的事实载荷。"""

    frame: int
    source_ref: str | None
    value: float

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "source_ref": self.source_ref,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class AuraInteractionResolvedPayload:
    """Reaction 驱动的 Aura 元素量变化已提交的事实载荷。"""

    result: AuraTransitionResult

    def to_dict(self) -> dict[str, object]:
        return {
            "interaction_id": self.result.interaction_id,
            "subject_ref": self.result.subject_ref.entity_id,
            "aura_kind": self.result.aura_kind.value,
            "amount_before": self.result.amount_before.to_dict(),
            "amount_consumed": self.result.amount_consumed.to_dict(),
            "amount_after": self.result.amount_after.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class AuraDepletedPayload:
    """Aura 自然衰减归零并移除 Component 的事实载荷。"""

    result: AuraTransitionResult

    def to_dict(self) -> dict[str, object]:
        return {
            "interaction_id": self.result.interaction_id,
            "subject_ref": self.result.subject_ref.entity_id,
            "aura_kind": self.result.aura_kind.value,
            "amount_before": self.result.amount_before.to_dict(),
            "amount_after": self.result.amount_after.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ReactionOccurredPayload:
    """无状态普通 Reaction occurrence 已提交的事实载荷。"""

    occurrence: ReactionOccurrence

    def to_dict(self) -> dict[str, object]:
        return {
            "occurrence_ref": self.occurrence.occurrence_ref,
            "parent_occurrence_ref": self.occurrence.parent_occurrence_ref,
            "interaction_id": self.occurrence.interaction_id,
            "reaction_key": self.occurrence.reaction_key,
            "direction_key": self.occurrence.direction_key,
            "profile_key": self.occurrence.profile_key,
            "effect_groups": tuple(
                _reaction_effect_group_to_dict(group) for group in self.occurrence.effect_groups
            ),
        }


def _reaction_effect_group_to_dict(group) -> dict[str, object]:
    from genshin_sim.core.systems.reaction.models import (
        OccurrenceCause,
        ScheduledStateTickCause,
    )

    cause = group.cause
    if isinstance(cause, OccurrenceCause):
        cause_payload: dict[str, object] = {
            "kind": "occurrence",
            "occurrence_ref": cause.occurrence_ref,
        }
    elif isinstance(cause, ScheduledStateTickCause):
        cause_payload = _scheduled_state_tick_cause_to_dict(cause)
    else:
        raise ValueError("Reaction Effect group 缺少受支持的因果来源")
    return {
        "effect_group_ref": group.effect_group_ref,
        "execution_scope": group.execution_scope.value,
        "cause": cause_payload,
        "effect_refs": tuple(effect.effect_ref for effect in group.effects),
        "suppressed_effect_refs": group.suppressed_effect_refs,
    }


def _scheduled_state_tick_cause_to_dict(cause) -> dict[str, object]:
    return {
        "kind": "scheduled_state_tick",
        "cause_ref": cause.cause_ref,
        "state_instance_ref": cause.state_instance_ref.value,
        "scheduled_frame": cause.scheduled_frame,
        "tick_kind": cause.tick_kind.value,
        "tick_index": cause.tick_index,
    }


@dataclass(frozen=True, slots=True)
class ReactionStateChangedPayload:
    """ReactionState 完整创建、替换或移除已提交的通用状态事实。"""

    change: ReactionStateChange

    def to_dict(self) -> dict[str, object]:
        return {
            "slot": self.change.slot_key.slot.value,
            "scope_key": self.change.slot_key.scope_key.value,
            "subject": {
                "kind": self.change.slot_key.subject_ref.kind.value,
                "entity_id": self.change.slot_key.subject_ref.entity_id,
            },
            "before": _reaction_state_to_dict(self.change.before),
            "after": _reaction_state_to_dict(self.change.after),
        }


def _reaction_state_to_dict(record: ReactionStateRecord | None) -> dict[str, object] | None:
    if record is None:
        return None
    from genshin_sim.core.systems.reaction.states import (
        BurningState,
        CrystallizeShardState,
        DendroCoreState,
        ElectroChargedState,
        LunarCageState,
        LunarCrystallizeAccumulatorState,
        LunarStormCloudState,
        QuickenState,
        SprawlingShotState,
    )

    if isinstance(record, ElectroChargedState):
        return {
            "instance_ref": record.instance_ref.value,
            "created_frame": record.created_frame,
            "created_by_occurrence_ref": record.created_by_occurrence_ref,
            "current_effect_owner": record.current_effect_owner.to_dict(),
            "captured_scaling_basis": _captured_basis_to_dict(record.captured_scaling_basis),
            "next_required_frame": record.next_required_frame,
            "next_tick_frame": record.next_tick_frame,
            "next_tick_index": record.next_tick_index,
            "revision": record.revision,
        }
    if isinstance(record, BurningState):
        return {
            "instance_ref": record.instance_ref.value,
            "burning_aura_link_ref": record.burning_aura_link_ref.link_key,
            "dendro_like_link_refs": [item.link_key for item in record.dendro_like_link_refs],
            "created_frame": record.created_frame,
            "created_by_occurrence_ref": record.created_by_occurrence_ref,
            "current_effect_owner": record.current_effect_owner.to_dict(),
            "captured_scaling_basis": _captured_basis_to_dict(record.captured_scaling_basis),
            "next_required_frame": record.next_required_frame,
            "next_dendro_like_depletion_frame": record.next_dendro_like_depletion_frame,
            "next_damage_tick_frame": record.next_damage_tick_frame,
            "next_damage_tick_index": record.next_damage_tick_index,
            "next_pyro_application_frame": record.next_pyro_application_frame,
            "next_pyro_application_index": record.next_pyro_application_index,
            "revision": record.revision,
        }
    if isinstance(record, QuickenState):
        return {
            "instance_ref": record.instance_ref.value,
            "quicken_aura_link_ref": record.quicken_aura_link_ref.link_key,
            "created_frame": record.created_frame,
            "created_by_occurrence_ref": record.created_by_occurrence_ref,
            "last_updated_by_occurrence_ref": record.last_updated_by_occurrence_ref,
            "next_required_frame": record.next_required_frame,
            "revision": record.revision,
        }
    if isinstance(record, CrystallizeShardState):
        return {
            "instance_ref": record.instance_ref.value,
            "space_entity_ref": record.space_entity_ref,
            "element": record.element.value,
            "created_by_occurrence_ref": record.created_by_occurrence_ref,
            "trigger_source": record.trigger_source.to_dict(),
            "captured_shield_basis": _captured_crystallize_basis_to_dict(
                record.captured_shield_basis
            ),
            "created_frame": record.created_frame,
            "expires_at_frame": record.expires_at_frame,
            "lifecycle_state": record.lifecycle_state.value,
            "terminal_frame": record.terminal_frame,
            "next_required_frame": record.next_required_frame,
            "revision": record.revision,
        }
    if isinstance(record, DendroCoreState):
        return {
            "instance_ref": record.instance_ref.value,
            "space_entity_ref": record.space_entity_ref,
            "created_by_occurrence_ref": record.created_by_occurrence_ref,
            "core_creator_ref": record.core_creator_ref.to_dict(),
            "dynamic_scaling_basis": _dynamic_basis_to_dict(record.dynamic_scaling_basis),
            "pool_scope": record.pool_scope,
            "created_frame": record.created_frame,
            "expires_at_frame": record.expires_at_frame,
            "creation_sequence": record.creation_sequence,
            "next_required_frame": record.next_required_frame,
            "revision": record.revision,
        }
    if isinstance(record, LunarStormCloudState):
        return {
            "instance_ref": record.instance_ref.value,
            "space_entity_ref": record.space_entity_ref,
            "created_by_occurrence_ref": record.created_by_occurrence_ref,
            "trigger_source_ref": record.trigger_source_ref.to_dict(),
            "team_ref": record.team_ref,
            "created_frame": record.created_frame,
            "expires_at_frame": record.expires_at_frame,
            "next_attack_frame": record.next_attack_frame,
            "next_attack_index": record.next_attack_index,
            "attack_interval_frames": record.attack_interval_frames,
            "next_required_frame": record.next_required_frame,
            "revision": record.revision,
        }
    if isinstance(record, LunarCageState):
        return {
            "instance_ref": record.instance_ref.value,
            "space_entity_ref": record.space_entity_ref,
            "created_by_occurrence_ref": record.created_by_occurrence_ref,
            "trigger_source_ref": record.trigger_source_ref.to_dict(),
            "team_ref": record.team_ref,
            "created_frame": record.created_frame,
            "last_harmony_frame": record.last_harmony_frame,
            "next_attack_frame": record.next_attack_frame,
            "expires_at_frame": record.expires_at_frame,
            "attack_index": record.attack_index,
            "next_required_frame": record.next_required_frame,
            "revision": record.revision,
        }
    if isinstance(record, LunarCrystallizeAccumulatorState):
        return {
            "instance_ref": record.instance_ref.value,
            "team_ref": record.team_ref,
            "subject": {
                "kind": record.subject_ref.kind.value,
                "entity_id": record.subject_ref.entity_id,
            },
            "pending_records": [
                {
                    "occurrence_ref": item.occurrence_ref,
                    "frame": item.frame,
                    "order": item.order,
                    "participant_refs": [
                        participant.to_dict() for participant in item.participant_refs
                    ],
                }
                for item in record.pending_records
            ],
            "max_layers": record.max_layers,
            "next_required_frame": record.next_required_frame,
            "revision": record.revision,
        }
    if isinstance(record, SprawlingShotState):
        return {
            "instance_ref": record.instance_ref.value,
            "space_entity_ref": record.space_entity_ref,
            "source_core_ref": record.source_core_ref.value,
            "trigger_source_ref": record.trigger_source_ref.to_dict(),
            "dynamic_scaling_basis": _dynamic_basis_to_dict(record.dynamic_scaling_basis),
            "selected_target": {
                "kind": record.selected_target_ref.kind.value,
                "entity_id": record.selected_target_ref.entity_id,
            },
            "created_frame": record.created_frame,
            "revision": record.revision,
        }
    payload: dict[str, object] = {
        "instance_ref": record.instance_ref.value,
        "decay_rate": record.decay_rate,
        "decay_rate_updated_frame": record.decay_rate_updated_frame,
        "next_required_frame": record.next_required_frame,
    }
    if record.slot_key.slot.value == "frozen":
        frozen = cast(_FrozenStateLike, record)
        payload["state_link_ref"] = frozen.state_link_ref.link_key
        payload["created_frame"] = frozen.created_frame
    return payload


def _captured_basis_to_dict(basis: CapturedTransformativeScalingBasis) -> dict[str, object]:
    """保持事件层对 Reaction 基础的序列化只读，不引入运行时写依赖。"""

    return {
        "basis_ref": basis.basis_ref,
        "captured_frame": basis.captured_frame,
        "source_ref": basis.source_ref.to_dict(),
        "source_kind": basis.source_kind.value,
        "source_level": basis.source_level,
        "elemental_mastery": basis.elemental_mastery,
        "reaction_bonus": basis.reaction_bonus,
        "reaction_profile_key": basis.reaction_profile_key,
        "damage_profile_key": basis.damage_profile_key,
        "level_multiplier_table_key": basis.level_multiplier_table_key,
        "level_multiplier": basis.level_multiplier,
        "source_observation_ref": basis.source_observation_ref,
        "source_owner_slot": basis.source_owner_slot,
    }


def _dynamic_basis_to_dict(basis: DynamicTransformativeScalingBasis) -> dict[str, object]:
    return {
        "basis_ref": basis.basis_ref,
        "source_ref": basis.source_ref.to_dict(),
        "source_observation_profile_key": basis.source_observation_profile_key,
        "reaction_profile_key": basis.reaction_profile_key,
        "damage_profile_key": basis.damage_profile_key,
        "reaction_bonus": basis.reaction_bonus,
    }


def _captured_crystallize_basis_to_dict(
    basis: CapturedCrystallizeShieldBasis,
) -> dict[str, object]:
    return {
        "source_ref": basis.source_ref.to_dict(),
        "captured_frame": basis.captured_frame,
        "source_level": basis.source_level,
        "source_elemental_mastery": basis.source_elemental_mastery,
        "crystallize_level_coefficient": basis.crystallize_level_coefficient,
        "elemental_mastery_bonus": basis.elemental_mastery_bonus,
        "native_absorption": basis.native_absorption,
    }


@dataclass(frozen=True, slots=True)
class ElementalInteractionResolvedPayload:
    """整批元素交互已完成状态提交和关联伤害结算的事实载荷。"""

    record: ElementalInteractionBatchRecord

    def to_dict(self) -> dict[str, object]:
        return {
            "batch_id": self.record.batch_id,
            "root_work_id": self.record.root_work_id,
            "settlement_round": self.record.settlement_round,
            "work_ids": list(self.record.work_ids),
            "icd_request_ids": list(self.record.icd_request_ids),
            "reaction_occurrence_refs": list(self.record.reaction_occurrence_refs),
            "reaction_decision_steps": [
                {
                    "interaction_id": step.interaction_id,
                    "step_ordinal": step.step_ordinal,
                    "selected_candidate_keys": list(step.selected_candidate_keys),
                    "occurrence_refs": list(step.occurrence_refs),
                    "state_transition_refs": list(step.state_transition_refs),
                    "state_planning_intent_refs": list(step.state_planning_intent_refs),
                }
                for step in self.record.reaction_decision_steps
            ],
            "current_impact_adjustment_refs": list(self.record.current_impact_adjustment_refs),
            "damage_request_ids": list(self.record.damage_request_ids),
            "batch_kind": self.record.batch_kind.value,
            "parent_work_id": self.record.parent_work_id,
            "parent_occurrence_refs": list(self.record.parent_occurrence_refs),
            "effect_group_refs": list(self.record.effect_group_refs),
            "effect_refs": list(self.record.effect_refs),
            "emission_batch_ref": self.record.emission_batch_ref,
            "generated_impact_refs": list(self.record.generated_impact_refs),
            "simultaneous_application_policy_keys": list(
                self.record.simultaneous_application_policy_keys
            ),
            "captured_source_observation_ref": self.record.captured_source_observation_ref,
            "target_effect_outcomes": [
                {
                    "target_order": outcome.target_order,
                    "subject_ref": {
                        "kind": outcome.subject_ref.kind.value,
                        "entity_id": outcome.subject_ref.entity_id,
                    },
                    "relation": outcome.relation.value,
                    "capabilities": sorted(capability.value for capability in outcome.capabilities),
                    "aura_outcome": outcome.aura_outcome,
                    "damage_outcome": outcome.damage_outcome,
                    "status_outcome": outcome.status_outcome,
                    "gate_resolution_ref": outcome.gate_resolution_ref,
                    "damage_request_id": outcome.damage_request_id,
                    "buff_request_id": outcome.buff_request_id,
                }
                for outcome in self.record.target_effect_outcomes
            ],
            "gate_resolution_refs": list(self.record.gate_resolution_refs),
            "buff_request_ids": list(self.record.buff_request_ids),
            "buff_instance_refs": list(self.record.buff_instance_refs),
            "follow_up_work_ids": list(self.record.follow_up_work_ids),
            "spatial_entity_refs": list(self.record.spatial_entity_refs),
            "reaction_state_binding_refs": list(self.record.reaction_state_binding_refs),
            "establishment_gate_resolution_refs": list(
                self.record.establishment_gate_resolution_refs
            ),
            "scheduled_root_work_id": self.record.scheduled_root_work_id,
            "scheduled_tick_index": self.record.scheduled_tick_index,
            "scheduled_root_outcome": self.record.scheduled_root_outcome,
            "scheduled_state_tick_causes": [
                _scheduled_state_tick_cause_to_dict(cause)
                for cause in self.record.scheduled_state_tick_causes
            ],
        }


@dataclass(frozen=True, slots=True)
class TeamSwitchedPayload:
    """队伍当前场上角色切换请求已经处理的事实载荷。"""

    requested_slot: int
    previous_slot: int | None
    active_slot: int
    accepted: bool
    status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_slot": self.requested_slot,
            "previous_slot": self.previous_slot,
            "active_slot": self.active_slot,
            "accepted": self.accepted,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class CooldownChangedPayload:
    """冷却充能或就绪帧已经变化的状态变化载荷。"""

    fact_id: str
    fact_kind: str
    frame: int
    subject_ref: dict[str, str]
    ability_key: str
    operation_id: str
    chain_id: str | None
    before_available_charges: int
    after_available_charges: int
    active_ready_frame: int | None
    queued_recoveries: int
    source_ref: str
    before_record: dict[str, object] | None = None
    after_record: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "fact_id": self.fact_id,
            "fact_kind": self.fact_kind,
            "frame": self.frame,
            "subject_ref": dict(self.subject_ref),
            "ability_key": self.ability_key,
            "operation_id": self.operation_id,
            "chain_id": self.chain_id,
            "before_available_charges": self.before_available_charges,
            "after_available_charges": self.after_available_charges,
            "active_ready_frame": self.active_ready_frame,
            "queued_recoveries": self.queued_recoveries,
            "source_ref": self.source_ref,
            "before_record": self.before_record,
            "after_record": self.after_record,
        }


@dataclass(frozen=True, slots=True)
class ContentStateChangedPayload:
    """宿主内容状态挂载已经提交补丁的状态变化载荷。"""

    frame: int
    owner_ref: str
    state_key: str
    fields: tuple[str, ...]
    before: Mapping[str, object]
    after: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "owner_ref": self.owner_ref,
            "state_key": self.state_key,
            "fields": tuple(sorted(self.fields)),
            "before": dict(self.before),
            "after": dict(self.after),
        }


@dataclass(frozen=True, slots=True)
class SpaceEntityCreatedPayload:
    """空间实体已经登记到 Space 的状态变化载荷。"""

    frame: int
    entity: SpatialEntity

    def to_dict(self) -> dict[str, object]:
        return {"frame": self.frame, "entity": self.entity.to_dict()}


@dataclass(frozen=True, slots=True)
class SpaceEntityRemovedPayload:
    """空间实体已经从 Space 移除的状态变化载荷。"""

    frame: int
    entity: SpatialEntity

    def to_dict(self) -> dict[str, object]:
        return {"frame": self.frame, "entity": self.entity.to_dict()}


@dataclass(frozen=True, slots=True)
class AttributePanelChangedPayload:
    """属性面板发生有效变化的状态变化载荷。"""

    frame: int
    subject_ref: dict[str, str]
    changes: tuple[AttributePanelChange, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "subject_ref": dict(self.subject_ref),
            "changes": tuple(change.to_dict() for change in self.changes),
        }
