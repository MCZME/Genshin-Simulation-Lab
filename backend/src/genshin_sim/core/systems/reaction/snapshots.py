"""Reaction Store 的 Gate 与持续 State 统一快照。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.systems.reaction.establishment_gates import ReactionEstablishmentGateRecord
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateRecord
from genshin_sim.core.systems.reaction.models import (
    CapturedCrystallizeShieldBasis,
    CapturedTransformativeScalingBasis,
    DynamicTransformativeScalingBasis,
    OccurrenceCause,
)
from genshin_sim.core.systems.reaction.resources import LunarBloomDewState
from genshin_sim.core.systems.reaction.states import (
    BurningState,
    CrystallizeShardState,
    DendroCoreState,
    ElectroChargedState,
    FrozenState,
    LunarCageState,
    LunarCrystallizeAccumulatorState,
    LunarStormCloudState,
    QuickenState,
    ReactionStateRecord,
    ScheduledStateTickCause,
    SprawlingShotState,
)


@dataclass(frozen=True, slots=True)
class ReactionSnapshot:
    frame: int
    normalized_through_frame: int
    version: int
    gate_records: tuple[ReactionDamageGateRecord, ...]
    state_records: tuple[ReactionStateRecord, ...]
    establishment_gate_records: tuple[ReactionEstablishmentGateRecord, ...] = ()
    lunar_bloom_dew_records: tuple[LunarBloomDewState, ...] = ()

    @property
    def records(self) -> tuple[ReactionDamageGateRecord, ...]:
        """保留 Gate Snapshot 的只读访问名。"""

        return self.gate_records

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "normalized_through_frame": self.normalized_through_frame,
            "version": self.version,
            "gate_records": [
                {
                    "gate_definition_key": record.slot_key.gate_definition_key,
                    "trigger_source": record.slot_key.trigger_source_ref.to_dict(),
                    "damage_target": {
                        "kind": record.slot_key.damage_target_ref.kind.value,
                        "entity_id": record.slot_key.damage_target_ref.entity_id,
                    },
                    "damage_kind_key": record.slot_key.damage_kind_key,
                    "window_started_frame": record.window_started_frame,
                    "ready_frame": record.ready_frame,
                    "accepted_count": record.accepted_count,
                    "last_accepted_frame": record.last_accepted_frame,
                    "last_occurrence_ref": record.last_occurrence_ref,
                    "last_effect_ref": record.last_effect_ref,
                    "cause": _cause_to_dict(record.cause),
                    "revision": record.revision,
                }
                for record in self.gate_records
            ],
            "state_records": [_state_record_to_dict(record) for record in self.state_records],
            "establishment_gate_records": [
                {
                    "gate_definition_key": record.slot_key.gate_definition_key,
                    "subject": {
                        "kind": record.slot_key.subject_ref.kind.value,
                        "entity_id": record.slot_key.subject_ref.entity_id,
                    },
                    "window_started_frame": record.window_started_frame,
                    "ready_frame": record.ready_frame,
                    "accepted_count": record.accepted_count,
                    "last_accepted_frame": record.last_accepted_frame,
                    "last_occurrence_ref": record.last_occurrence_ref,
                    "revision": record.revision,
                }
                for record in self.establishment_gate_records
            ],
            "lunar_bloom_dew_records": [
                record.to_dict() for record in self.lunar_bloom_dew_records
            ],
        }


def _state_record_to_dict(record: ReactionStateRecord) -> dict[str, object]:
    payload: dict[str, object] = {
        "slot": record.slot_key.slot.value,
        "scope_key": record.slot_key.scope_key.value,
        "subject": {
            "kind": record.subject_ref.kind.value,
            "entity_id": record.subject_ref.entity_id,
        },
        "instance_ref": record.instance_ref.value,
        "next_required_frame": record.next_required_frame,
    }
    if isinstance(record, FrozenState):
        payload["decay_rate"] = record.decay_rate
        payload["decay_rate_updated_frame"] = record.decay_rate_updated_frame
        payload["state_link_ref"] = record.state_link_ref.link_key
        payload["created_frame"] = record.created_frame
    elif isinstance(record, ElectroChargedState):
        payload.update(
            {
                "created_frame": record.created_frame,
                "created_by_occurrence_ref": record.created_by_occurrence_ref,
                "current_effect_owner": record.current_effect_owner.to_dict(),
                "captured_scaling_basis": _captured_basis_to_dict(record.captured_scaling_basis),
                "next_tick_frame": record.next_tick_frame,
                "next_tick_index": record.next_tick_index,
                "revision": record.revision,
            }
        )
    elif isinstance(record, BurningState):
        payload.update(
            {
                "burning_aura_link_ref": record.burning_aura_link_ref.link_key,
                "dendro_like_link_refs": [item.link_key for item in record.dendro_like_link_refs],
                "created_frame": record.created_frame,
                "created_by_occurrence_ref": record.created_by_occurrence_ref,
                "current_effect_owner": record.current_effect_owner.to_dict(),
                "captured_scaling_basis": _captured_basis_to_dict(record.captured_scaling_basis),
                "next_dendro_like_depletion_frame": record.next_dendro_like_depletion_frame,
                "next_damage_tick_frame": record.next_damage_tick_frame,
                "next_damage_tick_index": record.next_damage_tick_index,
                "next_pyro_application_frame": record.next_pyro_application_frame,
                "next_pyro_application_index": record.next_pyro_application_index,
                "revision": record.revision,
            }
        )
    elif isinstance(record, QuickenState):
        payload.update(
            {
                "quicken_aura_link_ref": record.quicken_aura_link_ref.link_key,
                "created_frame": record.created_frame,
                "created_by_occurrence_ref": record.created_by_occurrence_ref,
                "last_updated_by_occurrence_ref": record.last_updated_by_occurrence_ref,
                "revision": record.revision,
            }
        )
    elif isinstance(record, CrystallizeShardState):
        payload.update(
            {
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
                "revision": record.revision,
            }
        )
    elif isinstance(record, DendroCoreState):
        payload.update(
            {
                "space_entity_ref": record.space_entity_ref,
                "created_by_occurrence_ref": record.created_by_occurrence_ref,
                "core_creator_ref": record.core_creator_ref.to_dict(),
                "dynamic_scaling_basis": _dynamic_basis_to_dict(record.dynamic_scaling_basis),
                "pool_scope": record.pool_scope,
                "created_frame": record.created_frame,
                "expires_at_frame": record.expires_at_frame,
                "creation_sequence": record.creation_sequence,
                "revision": record.revision,
            }
        )
    elif isinstance(record, LunarStormCloudState):
        payload.update(
            {
                "space_entity_ref": record.space_entity_ref,
                "created_by_occurrence_ref": record.created_by_occurrence_ref,
                "trigger_source_ref": record.trigger_source_ref.to_dict(),
                "team_ref": record.team_ref,
                "created_frame": record.created_frame,
                "expires_at_frame": record.expires_at_frame,
                "next_attack_frame": record.next_attack_frame,
                "next_attack_index": record.next_attack_index,
                "attack_interval_frames": record.attack_interval_frames,
                "revision": record.revision,
            }
        )
    elif isinstance(record, LunarCageState):
        payload.update(
            {
                "space_entity_ref": record.space_entity_ref,
                "created_by_occurrence_ref": record.created_by_occurrence_ref,
                "trigger_source_ref": record.trigger_source_ref.to_dict(),
                "team_ref": record.team_ref,
                "created_frame": record.created_frame,
                "last_harmony_frame": record.last_harmony_frame,
                "next_attack_frame": record.next_attack_frame,
                "expires_at_frame": record.expires_at_frame,
                "attack_index": record.attack_index,
                "revision": record.revision,
            }
        )
    elif isinstance(record, LunarCrystallizeAccumulatorState):
        payload.update(
            {
                "team_ref": record.team_ref,
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
                "revision": record.revision,
            }
        )
    elif isinstance(record, SprawlingShotState):
        payload.update(
            {
                "space_entity_ref": record.space_entity_ref,
                "source_core_ref": record.source_core_ref.value,
                "trigger_occurrence_ref": record.trigger_occurrence_ref,
                "trigger_source_ref": record.trigger_source_ref.to_dict(),
                "dynamic_scaling_basis": _dynamic_basis_to_dict(record.dynamic_scaling_basis),
                "selected_target": {
                    "kind": record.selected_target_ref.kind.value,
                    "entity_id": record.selected_target_ref.entity_id,
                },
                "created_frame": record.created_frame,
                "revision": record.revision,
            }
        )
    else:
        payload["decay_rate"] = record.decay_rate
        payload["decay_rate_updated_frame"] = record.decay_rate_updated_frame
    return payload


def _cause_to_dict(cause: OccurrenceCause | ScheduledStateTickCause | None) -> dict[str, object]:
    if isinstance(cause, OccurrenceCause):
        return {"kind": "occurrence", "occurrence_ref": cause.occurrence_ref}
    if isinstance(cause, ScheduledStateTickCause):
        return {
            "kind": "scheduled_state_tick",
            "cause_ref": cause.cause_ref,
            "state_instance_ref": cause.state_instance_ref.value,
            "scheduled_frame": cause.scheduled_frame,
            "tick_kind": cause.tick_kind.value,
            "tick_index": cause.tick_index,
        }
    raise ValueError("Damage Gate 快照缺少 cause")


def _captured_basis_to_dict(basis: CapturedTransformativeScalingBasis) -> dict[str, object]:
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
