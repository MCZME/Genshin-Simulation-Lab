"""原激化、超激化、蔓激化与绽放机制簇的生产纵向 golden case。"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.config import SimulationConfig
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.coordination.elemental_reaction import (
    BloomCoreTriggerError,
    BloomCoreTriggerRequest,
    SprawlingShotResolutionRequest,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType, ReactionOccurredPayload
from genshin_sim.core.impacts import (
    DamageImpactSpec,
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.space import Vector3
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraDecayMode, AuraStrength
from genshin_sim.core.systems.damage import DamageElement, DamageScalingTerm, DamageType
from genshin_sim.core.systems.reaction import (
    GeneratedDamageImpactEffect,
    SprawlingShotResolution,
    UnsupportedDendroReactionCandidateError,
)
from genshin_sim.core.systems.reaction.mechanics.bloom.keys import (
    BLOOM_EXPLOSION_DAMAGE_KIND_KEY,
    BURGEON_DAMAGE_KIND_KEY,
    HYPERBLOOM_DAMAGE_KIND_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.catalyze.mechanic import (
    AGGRAVATE_PROFILE_KEY,
    AGGRAVATE_REACTION_KEY,
    CATALYZE_DAMAGE_FORMULA_KEY,
    SPREAD_PROFILE_KEY,
    SPREAD_REACTION_KEY,
)
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    write_minimal_static_asset_database,
)

CATALYZE_EM = 200.0
CATALYZE_LEVEL_MULTIPLIER = 1446.853
CATALYZE_SOURCE = ElementalSourceRef("golden:quicken-and-bloom")


@pytest.mark.parametrize(
    (
        "initial_aura",
        "trigger_element",
        "reaction_key",
        "reaction_profile_key",
        "reaction_multiplier",
    ),
    (
        (
            Element.DENDRO,
            Element.ELECTRO,
            AGGRAVATE_REACTION_KEY,
            AGGRAVATE_PROFILE_KEY,
            1.15,
        ),
        (
            Element.ELECTRO,
            Element.DENDRO,
            SPREAD_REACTION_KEY,
            SPREAD_PROFILE_KEY,
            1.25,
        ),
    ),
)
def test_damage_icd_aura_quicken_and_catalyze_formula_audit(
    tmp_path: Path,
    initial_aura: Element,
    trigger_element: Element,
    reaction_key: str,
    reaction_profile_key: str,
    reaction_multiplier: float,
) -> None:
    assembled = _assemble(tmp_path, elemental_mastery=CATALYZE_EM)
    target_ref = _target_subject()
    _apply_aura(assembled, initial_aura, "golden:catalyze:initial")

    establish_record = assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(
            trigger_element,
            "golden:catalyze:establish",
            main_attack_tag="testing.runtime_probe.direct",
        ),
    )
    established_quicken = assembled.aura_runtime.view(target_ref).component_for(AuraKind.QUICKEN)
    established_state = assembled.reaction_runtime.quicken_state_for(target_ref)

    assert established_quicken is not None
    assert established_quicken.current_amount == AuraAmount(Fraction(4, 5))
    assert established_state is not None
    assert establish_record.reaction_decision_steps[0].selected_candidate_keys == (
        "reaction.quicken",
    )

    catalyze_record = assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(
            trigger_element,
            "golden:catalyze:trigger",
            main_attack_tag=CATALYZE_DAMAGE_FORMULA_KEY,
        ),
    )
    result = assembled.damage_handler.records[-1].result
    quicken_after = assembled.aura_runtime.view(target_ref).component_for(AuraKind.QUICKEN)
    catalyze = result.catalyze_reaction_resolution

    assert catalyze_record.reaction_decision_steps[0].selected_candidate_keys == (reaction_key,)
    assert catalyze_record.reaction_decision_steps[0].occurrence_refs == (
        catalyze.occurrence_ref if catalyze is not None else "",
    )
    assert quicken_after == established_quicken
    assert assembled.reaction_runtime.quicken_state_for(target_ref) == established_state
    assert len(assembled.aura_icd_runtime.snapshot().records) == 1

    assert result.damage_type is DamageType.CATALYZE_REACTION
    assert catalyze is not None
    assert catalyze.target_impact_ref == "golden:catalyze:trigger:target:target_1"
    assert catalyze.reaction_profile_key == reaction_profile_key
    assert catalyze.trigger_element is trigger_element
    assert catalyze.source_level == 90
    assert catalyze.level_multiplier_table_key == "damage.transformative_level_multiplier.character"
    assert catalyze.level_multiplier == pytest.approx(CATALYZE_LEVEL_MULTIPLIER)
    assert catalyze.elemental_mastery == pytest.approx(CATALYZE_EM)
    assert catalyze.mastery_bonus == pytest.approx(5 / 7)
    assert catalyze.reaction_multiplier == pytest.approx(reaction_multiplier)
    expected_addition = CATALYZE_LEVEL_MULTIPLIER * reaction_multiplier * (1 + 5 / 7)
    assert catalyze.base_damage_addition.value == pytest.approx(expected_addition)
    assert result.base_damage == pytest.approx(200.0 + expected_addition)
    assert result.base_damage_additions == (catalyze.base_damage_addition,)
    assert result.damage_bonus_multiplier == pytest.approx(1.0)
    assert result.crit_multiplier == pytest.approx(1.0)
    assert result.defense.multiplier == pytest.approx(0.5)
    assert result.resistance.multiplier == pytest.approx(0.9)
    assert result.final_damage == pytest.approx((200.0 + expected_addition) * 0.5 * 0.9)


def test_quicken_decay_larger_coverage_and_natural_expiry(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    target_ref = _target_subject()
    _apply_aura(
        assembled,
        Element.DENDRO,
        "golden:quicken:initial",
        strength=AuraStrength.STRONG,
        elemental_amount=AuraAmount(3),
    )
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(
            Element.ELECTRO,
            "golden:quicken:establish",
            main_attack_tag="testing.runtime_probe.direct",
        ),
    )
    initial_quicken = assembled.aura_runtime.view(target_ref).component_for(AuraKind.QUICKEN)
    initial_state = assembled.reaction_runtime.quicken_state_for(target_ref)

    assert initial_quicken is not None
    assert initial_quicken.current_amount == AuraAmount.one()
    assert initial_state is not None
    remaining_dendro = assembled.aura_runtime.view(target_ref).component_for(AuraKind.DENDRO)
    assert remaining_dendro is not None
    assert remaining_dendro.current_amount == AuraAmount(Fraction(7, 5))

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 1)
    decayed_quicken = assembled.aura_runtime.view(target_ref).component_for(AuraKind.QUICKEN)

    assert decayed_quicken is not None
    assert decayed_quicken.current_amount == AuraAmount(Fraction(659, 660))

    coverage_record = assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(
            Element.ELECTRO,
            "golden:quicken:coverage",
            frame=1,
            main_attack_tag=CATALYZE_DAMAGE_FORMULA_KEY,
        ),
    )
    covered_quicken = assembled.aura_runtime.view(target_ref).component_for(AuraKind.QUICKEN)
    covered_state = assembled.reaction_runtime.quicken_state_for(target_ref)

    assert tuple(
        step.selected_candidate_keys for step in coverage_record.reaction_decision_steps
    ) == (
        (AGGRAVATE_REACTION_KEY,),
        ("reaction.quicken",),
    )
    assert covered_quicken is not None
    assert covered_state is not None
    assert covered_quicken.instance_ref == initial_quicken.instance_ref
    assert covered_state.instance_ref == initial_state.instance_ref
    assert covered_state.revision == initial_state.revision + 1
    assert covered_quicken.current_amount > decayed_quicken.current_amount

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 1_000)

    assert assembled.aura_runtime.view(target_ref).component_for(AuraKind.QUICKEN) is None
    assert assembled.reaction_runtime.quicken_state_for(target_ref) is None


def test_quicken_and_dendro_burning_deplete_independently_and_recover(
    tmp_path: Path,
) -> None:
    recovery = _assemble(tmp_path)
    recovery_target = _establish_quicken_with_remaining_dendro(recovery)
    _establish_burning(recovery, request_id="golden:quicken-burning:recovery")
    recovery_burning = recovery.reaction_runtime.burning_state_for(recovery_target)
    recovery_view = recovery.aura_runtime.view(recovery_target)
    recovery_quicken = recovery_view.component_for(AuraKind.QUICKEN)
    recovery_dendro = recovery_view.component_for(AuraKind.DENDRO)

    assert recovery_burning is not None
    assert recovery_quicken is not None
    assert recovery_dendro is not None
    assert recovery_quicken.decay_mode is AuraDecayMode.REACTION_MANAGED
    assert recovery_dendro.decay_mode is AuraDecayMode.REACTION_MANAGED
    assert len(recovery_burning.dendro_like_link_refs) == 2

    _consume_aura(
        recovery,
        aura_kind=AuraKind.BURNING,
        amount=AuraAmount(Fraction(19, 10)),
        operation_id="golden:quicken-burning:deplete-burning",
    )
    recovery.elemental_settlement_coordinator.settle_aura_impact(
        recovery.context,
        _aura_request(Element.CRYO, "golden:quicken-burning:recover"),
    )
    recovered_view = recovery.aura_runtime.view(recovery_target)
    recovered_quicken = recovered_view.component_for(AuraKind.QUICKEN)
    recovered_dendro = recovered_view.component_for(AuraKind.DENDRO)

    assert recovery.reaction_runtime.burning_state_for(recovery_target) is None
    assert recovered_quicken is not None
    assert recovered_dendro is not None
    assert recovered_quicken.decay_mode is AuraDecayMode.STANDARD
    assert recovered_dendro.decay_mode is AuraDecayMode.STANDARD

    depletion_path = tmp_path / "depletion"
    depletion_path.mkdir()
    depletion = _assemble(depletion_path)
    depletion_target = _establish_quicken_with_remaining_dendro(depletion)
    _establish_burning(depletion, request_id="golden:quicken-burning:depletion")

    _advance_to(depletion, 150)
    depleted_view = depletion.aura_runtime.view(depletion_target)
    remaining_dendro = depleted_view.component_for(AuraKind.DENDRO)

    assert depleted_view.component_for(AuraKind.QUICKEN) is None
    assert depletion.reaction_runtime.quicken_state_for(depletion_target) is None
    assert depletion.reaction_runtime.burning_state_for(depletion_target) is not None
    assert remaining_dendro is not None
    assert remaining_dendro.decay_mode is AuraDecayMode.REACTION_MANAGED


def test_anemo_on_quicken_is_rejected_before_writing(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    target_ref = _establish_quicken(assembled)
    aura_before = assembled.aura_runtime.snapshot()
    reaction_before = assembled.reaction_runtime.snapshot(0)
    icd_before = assembled.aura_icd_runtime.snapshot()
    damage_count = len(assembled.damage_handler.records)

    with pytest.raises(
        UnsupportedDendroReactionCandidateError,
        match="雷/风扩散进入未实现的激化扩散候选",
    ):
        assembled.elemental_settlement_coordinator.settle_aura_impact(
            assembled.context,
            _aura_request(Element.ANEMO, "golden:unsupported:anemo"),
        )

    assert assembled.aura_runtime.snapshot() == aura_before
    assert assembled.reaction_runtime.snapshot(0) == reaction_before
    assert assembled.aura_icd_runtime.snapshot() == icd_before
    assert len(assembled.damage_handler.records) == damage_count
    assert assembled.reaction_runtime.quicken_state_for(target_ref) is not None


def test_hydro_on_dendro_creates_a_bound_dendro_core(tmp_path: Path) -> None:
    assembled = _assemble(tmp_path)
    target_ref = _target_subject()
    _apply_aura(assembled, Element.DENDRO, "golden:bloom:seed")

    record = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "golden:bloom:trigger"),
    )

    core = assembled.reaction_runtime.active_dendro_cores()[0]
    remaining_dendro = assembled.aura_runtime.view(target_ref).component_for(AuraKind.DENDRO)
    assert len(record.reaction_occurrence_refs) == 1
    assert record.reaction_occurrence_refs[0].endswith(":occurrence:0")
    assert core.core_creator_ref.source_key == "character:slot_1"
    assert core.created_frame == 0
    assert core.expires_at_frame == 360
    assert core.creation_sequence == 1
    assert assembled.space_runtime.get_entity(core.space_entity_ref) is not None
    assert remaining_dendro is not None
    assert remaining_dendro.current_amount == AuraAmount(Fraction(3, 10))


def test_expired_core_removes_binding_then_settles_bloom_damage(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    _apply_aura(assembled, Element.DENDRO, "golden:bloom-expiry:seed")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "golden:bloom-expiry:trigger"),
    )
    core = assembled.reaction_runtime.active_dendro_cores()[0]

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 360)

    assert assembled.reaction_runtime.dendro_core_state_for(core.instance_ref) is None
    assert assembled.space_runtime.get_entity(core.space_entity_ref) is None
    damage_record = assembled.damage_handler.records[-1]
    assert damage_record.damage_request.profile_key == "damage_profile.reaction.bloom_explosion"
    assert damage_record.damage_request.target_ref.entity_id == "target:target_1"
    character_record = _character_damage_record(assembled)
    assert character_record.result.reaction_details is not None
    assert character_record.result.reaction_details.base_multiplier == pytest.approx(0.1)
    damage_taken = assembled.character_damage_taken_coordinator.records[-1]
    assert damage_taken.incoming_damage.amount == pytest.approx(
        character_record.result.final_damage
    )
    assert damage_taken.health_result.effective_amount == pytest.approx(
        character_record.result.final_damage
    )
    occurrence = next(
        payload.occurrence
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.REACTION_OCCURRED
        and isinstance(payload := event.payload, ReactionOccurredPayload)
        and payload.occurrence.reaction_key == "reaction.bloom_explosion"
    )
    assert occurrence.direction_key == "expired"
    assert occurrence.parent_occurrence_ref == core.created_by_occurrence_ref
    assert occurrence.effect_groups[0].parent_occurrence_ref == occurrence.occurrence_ref
    effect = occurrence.effect_groups[0].effects[0]
    assert isinstance(effect, GeneratedDamageImpactEffect)
    assert effect.damage_kind_key == BLOOM_EXPLOSION_DAMAGE_KIND_KEY


def test_sixth_core_evicts_oldest_and_settles_bloom_damage(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    created = tuple(
        _create_bloom_core(assembled, f"golden:bloom-capacity:{index}") for index in range(6)
    )

    active = assembled.reaction_runtime.active_dendro_cores()
    assert len(active) == 5
    assert created[0].instance_ref not in {core.instance_ref for core in active}
    assert [core.creation_sequence for core in active] == [2, 3, 4, 5, 6]
    assert assembled.space_runtime.get_entity(created[0].space_entity_ref) is None
    assert assembled.damage_handler.records[-1].damage_request.profile_key == (
        "damage_profile.reaction.bloom_explosion"
    )
    occurrence = next(
        payload.occurrence
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.REACTION_OCCURRED
        and isinstance(payload := event.payload, ReactionOccurredPayload)
        and payload.occurrence.direction_key == "capacity_evicted"
    )
    assert occurrence.parent_occurrence_ref == created[0].created_by_occurrence_ref


def test_burgeon_contact_terminates_confirmed_core_and_settles_damage(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    core = _create_bloom_core(assembled, "golden:burgeon")

    result = assembled.elemental_settlement_coordinator.trigger_bloom_cores(
        assembled.context,
        _bloom_core_trigger_request(
            assembled,
            operation_id="golden:burgeon:contact",
            incoming_element=Element.PYRO,
            contacted_core_refs=(core.instance_ref,),
        ),
    )

    assert result.terminated_core_refs == (core.instance_ref,)
    assert not result.created_shot_refs
    assert assembled.reaction_runtime.dendro_core_state_for(core.instance_ref) is None
    assert assembled.space_runtime.get_entity(core.space_entity_ref) is None
    assert assembled.damage_handler.records[-1].damage_request.profile_key == (
        "damage_profile.reaction.burgeon"
    )
    character_record = _character_damage_record(assembled)
    assert character_record.result.reaction_details is not None
    assert character_record.result.reaction_details.base_multiplier == pytest.approx(0.15)
    assert assembled.character_damage_taken_coordinator.records[-1].incoming_damage.amount == (
        pytest.approx(character_record.result.final_damage)
    )
    assert len(result.occurrences) == 1
    occurrence = result.occurrences[0]
    assert occurrence.reaction_key == "reaction.burgeon"
    assert occurrence.direction_key == "burgeon_triggered"
    assert occurrence.parent_occurrence_ref == core.created_by_occurrence_ref
    effect = result.effect_groups[0].effects[0]
    assert isinstance(effect, GeneratedDamageImpactEffect)
    assert effect.damage_kind_key == BURGEON_DAMAGE_KIND_KEY


def test_hyperbloom_locks_target_then_settles_arrival_damage(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    core = _create_bloom_core(assembled, "golden:hyperbloom")
    core_entity = assembled.space_runtime.get_entity(core.space_entity_ref)
    assert core_entity is not None
    trigger = assembled.elemental_settlement_coordinator.trigger_bloom_cores(
        assembled.context,
        _bloom_core_trigger_request(
            assembled,
            operation_id="golden:hyperbloom:contact",
            incoming_element=Element.ELECTRO,
            contacted_core_refs=(core.instance_ref,),
        ),
    )

    assert trigger.terminated_core_refs == (core.instance_ref,)
    assert len(trigger.created_shot_refs) == 1
    shot_ref = trigger.created_shot_refs[0]
    shot = assembled.reaction_runtime.sprawling_shot_state_for(shot_ref)
    assert shot is not None
    assert shot.selected_target_ref == _target_subject()
    assert len(trigger.occurrences) == 1
    assert trigger.occurrences[0].reaction_key == "reaction.hyperbloom"
    assert trigger.occurrences[0].direction_key == "hyperbloom_triggered"
    arrival = assembled.elemental_settlement_coordinator.resolve_sprawling_shot(
        assembled.context,
        SprawlingShotResolutionRequest(
            operation_id="golden:hyperbloom:arrival",
            shot_ref=shot_ref,
            frame=0,
            resolution=SprawlingShotResolution.ARRIVED,
            impact_position=core_entity.position,
        ),
    )

    assert len(arrival.effect_groups) == 1
    assert assembled.reaction_runtime.sprawling_shot_state_for(shot_ref) is None
    assert assembled.space_runtime.get_entity(shot.space_entity_ref) is None
    assert assembled.damage_handler.records[-1].damage_request.profile_key == (
        "damage_profile.reaction.hyperbloom"
    )
    assert assembled.character_damage_taken_coordinator.records == ()
    assert len(arrival.occurrences) == 1
    assert arrival.occurrences[0].direction_key == "arrived"
    assert arrival.occurrences[0].parent_occurrence_ref == shot.trigger_occurrence_ref
    effect = arrival.effect_groups[0].effects[0]
    assert isinstance(effect, GeneratedDamageImpactEffect)
    assert effect.damage_kind_key == HYPERBLOOM_DAMAGE_KIND_KEY


def test_bloom_core_contact_requires_matching_committed_impact(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    core = _create_bloom_core(assembled, "golden:bloom-contact-evidence")
    request = _bloom_core_trigger_request(
        assembled,
        operation_id="golden:bloom-contact-evidence:valid",
        incoming_element=Element.ELECTRO,
        contacted_core_refs=(core.instance_ref,),
    )
    invalid_requests = (
        replace(
            request,
            operation_id="golden:bloom-contact-evidence:missing",
            associated_impact_ref=None,
        ),
        replace(
            request,
            operation_id="golden:bloom-contact-evidence:unknown",
            associated_impact_ref="golden:bloom-contact-evidence:unknown-impact",
        ),
        replace(
            request,
            operation_id="golden:bloom-contact-evidence:source",
            source_ref=ElementalSourceRef("character:slot_1", "different-impact"),
        ),
        replace(
            request,
            operation_id="golden:bloom-contact-evidence:element",
            incoming_element=Element.PYRO,
        ),
        replace(
            request,
            operation_id="golden:bloom-contact-evidence:amount",
            incoming_amount=AuraAmount(Fraction(1, 2)),
        ),
    )

    for invalid in invalid_requests:
        with pytest.raises(BloomCoreTriggerError, match="Impact|impact"):
            assembled.bloom_core_trigger_coordinator.trigger(assembled.context, invalid)

    assert assembled.reaction_runtime.dendro_core_state_for(core.instance_ref) == core
    assert assembled.space_runtime.get_entity(core.space_entity_ref) is not None


@pytest.mark.parametrize(
    ("target_distance", "expects_shot"),
    ((15.0, True), (15.001, False)),
)
def test_hyperbloom_uses_confirmed_fifteen_meter_target_boundary(
    tmp_path: Path,
    target_distance: float,
    expects_shot: bool,
) -> None:
    assembled = _assemble(tmp_path)
    core = _create_bloom_core(assembled, "golden:hyperbloom-search-boundary")
    target_entity = assembled.space_runtime.get_entity("target:target_1")
    assert target_entity is not None
    assembled.space_runtime.update_entity(
        replace(target_entity, position=Vector3(target_distance, 0.0, 0.0))
    )

    trigger = assembled.elemental_settlement_coordinator.trigger_bloom_cores(
        assembled.context,
        _bloom_core_trigger_request(
            assembled,
            operation_id="golden:hyperbloom:search-boundary",
            incoming_element=Element.ELECTRO,
            contacted_core_refs=(core.instance_ref,),
        ),
    )

    assert trigger.terminated_core_refs == (core.instance_ref,)
    assert bool(trigger.created_shot_refs) is expects_shot


def test_hyperbloom_selects_nearest_target_within_search_range(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path, target_positions=(0.0, 10.0))
    core = _create_bloom_core(assembled, "golden:hyperbloom-nearest-target")
    first_target = assembled.space_runtime.get_entity("target:target_1")
    assert first_target is not None
    assembled.space_runtime.update_entity(replace(first_target, position=Vector3(14.0, 0.0, 0.0)))

    trigger = assembled.elemental_settlement_coordinator.trigger_bloom_cores(
        assembled.context,
        _bloom_core_trigger_request(
            assembled,
            operation_id="golden:hyperbloom:nearest-target",
            incoming_element=Element.ELECTRO,
            contacted_core_refs=(core.instance_ref,),
        ),
    )

    shot = assembled.reaction_runtime.sprawling_shot_state_for(trigger.created_shot_refs[0])
    assert shot is not None
    assert shot.selected_target_ref == ElementalSubjectRef.target("target:target_2")


def test_hyperbloom_arrival_requires_locked_target_within_one_meter(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    core = _create_bloom_core(assembled, "golden:hyperbloom-out-of-range")
    trigger = assembled.elemental_settlement_coordinator.trigger_bloom_cores(
        assembled.context,
        _bloom_core_trigger_request(
            assembled,
            operation_id="golden:hyperbloom-out-of-range:contact",
            incoming_element=Element.ELECTRO,
            contacted_core_refs=(core.instance_ref,),
        ),
    )
    shot_ref = trigger.created_shot_refs[0]
    damage_count = len(assembled.damage_handler.records)

    result = assembled.elemental_settlement_coordinator.resolve_sprawling_shot(
        assembled.context,
        SprawlingShotResolutionRequest(
            operation_id="golden:hyperbloom-out-of-range:arrival",
            shot_ref=shot_ref,
            frame=0,
            resolution=SprawlingShotResolution.ARRIVED,
            impact_position=Vector3(100.0, 0.0, 100.0),
        ),
    )

    assert len(result.occurrences) == 1
    assert result.occurrences[0].direction_key == "arrived"
    assert len(assembled.damage_handler.records) == damage_count


def test_character_damage_prevalidation_does_not_consume_gate(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    _create_bloom_core(assembled, "golden:bloom-character-prevalidation")
    damage_count = len(assembled.damage_handler.records)
    gate_records = assembled.reaction_runtime.gate_records
    assembled.elemental_settlement_coordinator.character_damage_taken_coordinator = None

    with pytest.raises(RuntimeError, match="CharacterDamageTakenCoordinator"):
        assembled.elemental_settlement_coordinator.update_frame(assembled.context, 360)

    assert len(assembled.damage_handler.records) == damage_count
    assert assembled.reaction_runtime.gate_records == gate_records


def test_hydro_rejects_unconfirmed_dendro_and_quicken_coexistence(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    _establish_quicken_with_remaining_dendro(assembled)
    aura_before = assembled.aura_runtime.snapshot()
    reaction_before = assembled.reaction_runtime.snapshot(0)

    with pytest.raises(
        UnsupportedDendroReactionCandidateError,
        match="同时进入普通草与激元素绽放候选",
    ):
        assembled.elemental_settlement_coordinator.settle_aura_impact(
            assembled.context,
            _aura_request(Element.HYDRO, "golden:bloom-ambiguous-hydro"),
        )

    assert assembled.aura_runtime.snapshot() == aura_before
    assert assembled.reaction_runtime.snapshot(0) == reaction_before


def test_dendro_on_electro_charged_runs_quicken_then_two_blooms(
    tmp_path: Path,
) -> None:
    assembled = _assemble(tmp_path)
    _apply_aura(
        assembled,
        Element.HYDRO,
        "golden:electro-charged-bloom:hydro",
        elemental_amount=AuraAmount(2),
    )
    _apply_aura(assembled, Element.ELECTRO, "golden:electro-charged-bloom:electro")

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(
            Element.DENDRO,
            "golden:electro-charged-bloom:dendro",
            elemental_amount=AuraAmount(Fraction(6, 5)),
        ),
    )

    cores = assembled.reaction_runtime.active_dendro_cores()
    assert len(cores) == 2
    assert cores[0].core_creator_ref == cores[1].core_creator_ref
    assert cores[0].core_creator_ref.source_key == "character:slot_1"
    assert assembled.reaction_runtime.quicken_state_for(_target_subject()) is not None
    assert assembled.aura_runtime.view(_target_subject()).component_for(AuraKind.HYDRO) is None


def _establish_quicken(assembled) -> ElementalSubjectRef:
    target_ref = _target_subject()
    _apply_aura(assembled, Element.DENDRO, "golden:quicken:seed")
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(
            Element.ELECTRO,
            "golden:quicken:establish",
            main_attack_tag="testing.runtime_probe.direct",
        ),
    )
    assert assembled.reaction_runtime.quicken_state_for(target_ref) is not None
    return target_ref


def _create_bloom_core(assembled, request_prefix: str):
    _apply_aura(assembled, Element.DENDRO, f"{request_prefix}:seed")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, f"{request_prefix}:trigger"),
    )
    return assembled.reaction_runtime.active_dendro_cores()[0]


def _bloom_core_trigger_request(
    assembled,
    *,
    operation_id: str,
    incoming_element: Element,
    contacted_core_refs,
    incoming_amount: AuraAmount | None = None,
) -> BloomCoreTriggerRequest:
    resolved_amount = AuraAmount.one() if incoming_amount is None else incoming_amount
    associated_impact_ref = f"{operation_id}:impact"
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(
            incoming_element,
            associated_impact_ref,
            elemental_amount=resolved_amount,
        ),
    )
    return BloomCoreTriggerRequest(
        operation_id=operation_id,
        frame=0,
        source_ref=ElementalSourceRef("character:slot_1", associated_impact_ref),
        incoming_element=incoming_element,
        incoming_amount=resolved_amount,
        contacted_core_refs=contacted_core_refs,
        associated_impact_ref=associated_impact_ref,
    )


def _establish_quicken_with_remaining_dendro(assembled) -> ElementalSubjectRef:
    target_ref = _target_subject()
    _apply_aura(
        assembled,
        Element.DENDRO,
        "golden:quicken-burning:seed",
        strength=AuraStrength.STRONG,
        elemental_amount=AuraAmount(3),
    )
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(
            Element.ELECTRO,
            "golden:quicken-burning:establish",
            main_attack_tag="testing.runtime_probe.direct",
        ),
    )
    assert assembled.aura_runtime.view(target_ref).component_for(AuraKind.QUICKEN) is not None
    assert assembled.aura_runtime.view(target_ref).component_for(AuraKind.DENDRO) is not None
    return target_ref


def _establish_burning(assembled, *, request_id: str) -> None:
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.PYRO, request_id),
    )


def _consume_aura(
    assembled,
    *,
    aura_kind: AuraKind,
    amount: AuraAmount,
    operation_id: str,
) -> None:
    planner = assembled.aura_runtime.begin_batch(0, operation_id)
    planner.consume(
        interaction_id=operation_id,
        subject_ref=_target_subject(),
        aura_kind=aura_kind,
        amount=amount,
    )
    assembled.aura_runtime.commit_prevalidated(planner.seal())


def _advance_to(assembled, frame: int) -> None:
    current = assembled.reaction_runtime.normalized_through_frame
    while current < frame:
        next_required = assembled.reaction_runtime.next_required_frame()
        if next_required is None or next_required > frame:
            assembled.elemental_settlement_coordinator.update_frame(assembled.context, frame)
            return
        assembled.elemental_settlement_coordinator.update_frame(assembled.context, next_required)
        current = assembled.reaction_runtime.normalized_through_frame


def _apply_aura(
    assembled,
    element: Element,
    request_id: str,
    *,
    strength: AuraStrength = AuraStrength.WEAK,
    elemental_amount: AuraAmount | None = None,
) -> None:
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            request_id,
            f"{request_id}:application",
            f"{request_id}:impact",
            0,
            0,
            CATALYZE_SOURCE,
            _target_subject(),
            element,
            strength,
            effective_raw_amount=elemental_amount,
        )
    )


def _damage_request(
    element: Element,
    request_id: str,
    *,
    main_attack_tag: str,
    frame: int = 0,
) -> ImpactRequest:
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.DAMAGE,
        impact_key="golden.reactions.damage",
        owner_slot=1,
        request_id=request_id,
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref=request_id,
            main_attack_tag=main_attack_tag,
            element=DamageElement(element.value),
            scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
            can_crit=False,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
            icd_label_key="golden.reactions.damage",
            icd_definition_key="icd.none",
        ),
    )


def _aura_request(
    element: Element,
    request_id: str,
    *,
    elemental_amount: AuraAmount | None = None,
) -> ImpactRequest:
    return ImpactRequest(
        frame=0,
        kind=ImpactKind.APPLY_AURA,
        impact_key="golden.reactions.application",
        owner_slot=1,
        request_id=request_id,
        target_refs=("target_1",),
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref=request_id,
            element=element,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=(AuraAmount.one() if elemental_amount is None else elemental_amount),
        ),
    )


def _target_subject() -> ElementalSubjectRef:
    return ElementalSubjectRef.target("target:target_1")


def _character_damage_record(assembled):
    return next(
        record
        for record in assembled.damage_handler.records
        if record.damage_request.target_ref.kind.value == "character"
    )


def _assemble(
    tmp_path: Path,
    *,
    elemental_mastery: float = 0.0,
    target_positions: tuple[float, ...] = (0.0,),
):
    asset_db = tmp_path / "assets.db"
    write_minimal_static_asset_database(asset_db)
    with sqlite3.connect(asset_db) as connection:
        cursor = connection.execute(
            """
            UPDATE character_level_stats
            SET ascension_stat = ?, ascension_value = ?
            WHERE character_key = ? AND level = ?
            """,
            ("elemental_mastery", elemental_mastery, "character:test_character", 90),
        )
    assert cursor.rowcount == 1
    return SimulationAssembler(
        SQLiteAssetRepository(asset_db),
    ).assemble(
        SimulationConfig.from_mapping(
            {
                "schema_version": 1,
                "kind": "simulation_config",
                "meta": {"name": "quicken and bloom golden", "description": ""},
                "team": [
                    {
                        "slot": 1,
                        "character": {
                            "asset_key": "character:test_character",
                            "level": 90,
                            "constellation": 0,
                            "talents": {"normal_attack": 1},
                        },
                        "artifacts": {"sets": [], "stats": {}},
                    }
                ],
                "scene": {
                    "targets": [
                        {
                            "id": f"target_{index}",
                            "level": 90,
                            "position": {"x": position_x, "y": 0, "z": 0},
                            "resistance": {"electro": 0.1, "dendro": 0.1},
                        }
                        for index, position_x in enumerate(target_positions, start=1)
                    ]
                },
                "input_trace": [],
                "rules": {"enabled": []},
                "run_options": {"max_frames": 1_000},
            }
        )
    )
