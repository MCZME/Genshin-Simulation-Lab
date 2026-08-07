from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.config import SimulationConfig
from genshin_sim.core.coordination.elemental_reaction import (
    DefaultReactionTargetEligibilityPort,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import (
    ElementalInteractionResolvedPayload,
    EventType,
    ReactionOccurredPayload,
)
from genshin_sim.core.impacts import ElementalApplicationSpec, ImpactKind, ImpactRequest
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraStrength
from genshin_sim.core.systems.damage import DamageType
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    write_minimal_static_asset_database,
)


def test_electro_charged_establishes_dual_aura_state_and_current_frame_pulse(tmp_path: Path):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    _apply_aura(assembled, target_ref, Element.ELECTRO, "initial:electro")

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:hydro"),
    )

    state = assembled.reaction_runtime.electro_charged_state_for(target_ref)
    assert state is not None
    assert state.next_tick_frame == 60
    assert state.next_tick_index == 1
    aura = assembled.aura_runtime.view(target_ref)
    hydro = aura.component_for(AuraKind.HYDRO)
    electro = aura.component_for(AuraKind.ELECTRO)
    assert hydro is not None
    assert electro is not None
    assert hydro.current_amount == AuraAmount("6/5")
    assert electro.current_amount == AuraAmount("6/5")
    results = _reaction_results(assembled)
    assert len(results) == 1
    assert results[0].final_damage == pytest.approx(2893.706)
    assert results[0].reaction_details is not None
    assert results[0].reaction_details.base_multiplier == 2.0
    assert results[0].crit_outcome.value == "not_applicable"


def test_electro_charged_establishes_from_electro_on_hydro(tmp_path: Path):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    _apply_aura(assembled, target_ref, Element.HYDRO, "initial:hydro")

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.ELECTRO, "electro-charged:electro"),
    )

    state = assembled.reaction_runtime.electro_charged_state_for(target_ref)
    assert state is not None
    aura = assembled.aura_runtime.view(target_ref)
    hydro = aura.component_for(AuraKind.HYDRO)
    electro = aura.component_for(AuraKind.ELECTRO)
    assert hydro is not None
    assert electro is not None
    assert hydro.current_amount == AuraAmount("6/5")
    assert electro.current_amount == AuraAmount("6/5")
    results = _reaction_results(assembled)
    assert len(results) == 1
    assert results[0].reaction_details is not None
    assert results[0].reaction_details.base_multiplier == 2.0


def test_electro_charged_reattachment_refreshes_owner_without_extra_pulse(tmp_path: Path):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    _apply_aura(assembled, target_ref, Element.ELECTRO, "initial:electro")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:first"),
    )
    before = assembled.reaction_runtime.electro_charged_state_for(target_ref)
    assert before is not None

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:refresh", frame=1),
    )

    after = assembled.reaction_runtime.electro_charged_state_for(target_ref)
    assert after is not None
    assert after.instance_ref == before.instance_ref
    assert after.next_tick_frame == 60
    assert after.next_tick_index == 1
    assert after.revision == before.revision + 1
    assert len(_reaction_results(assembled)) == 1


def test_electro_charged_scheduled_root_runs_before_frame_impacts(tmp_path: Path):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    _apply_aura(assembled, target_ref, Element.ELECTRO, "initial:electro")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:first"),
    )

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 60)

    state = assembled.reaction_runtime.electro_charged_state_for(target_ref)
    assert state is not None
    assert state.next_tick_frame == 120
    assert state.next_tick_index == 2
    results = _reaction_results(assembled)
    assert len(results) == 2
    assert results[1].reaction_details is not None
    assert results[1].reaction_details.base_multiplier == 2.0
    roots = tuple(
        record
        for record in assembled.elemental_settlement_coordinator.records
        if record.batch_kind.value == "scheduled_reaction_root"
    )
    assert len(roots) == 1
    assert roots[0].scheduled_tick_index == 1
    assert roots[0].scheduled_root_outcome == "prepared"
    assert len(roots[0].scheduled_state_tick_causes) == 1
    cause = roots[0].scheduled_state_tick_causes[0]
    assert cause.tick_kind.value == "electro_charged_pulse"
    assert cause.scheduled_frame == 60
    pulse = next(
        record
        for record in assembled.elemental_settlement_coordinator.records
        if record.batch_kind.value == "reaction_effect_group"
        and record.parent_work_id == roots[0].root_work_id
    )
    assert pulse.parent_occurrence_refs == ()
    scheduled_event = next(
        event
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.ELEMENTAL_INTERACTION_RESOLVED
        and isinstance(event.payload, ElementalInteractionResolvedPayload)
        and event.payload.record.scheduled_root_work_id == roots[0].scheduled_root_work_id
    )
    scheduled_payload = scheduled_event.payload.to_dict()
    assert scheduled_payload["scheduled_tick_index"] == 1
    assert scheduled_payload["scheduled_root_outcome"] == "prepared"


def test_electro_charged_due_root_is_settled_before_a_same_frame_raw_impact(tmp_path: Path):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    _apply_aura(assembled, target_ref, Element.ELECTRO, "initial:electro")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:first"),
    )

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:same-frame", frame=60),
    )

    records = assembled.elemental_settlement_coordinator.records
    scheduled_index = next(
        index
        for index, record in enumerate(records)
        if record.batch_kind.value == "scheduled_reaction_root"
    )
    raw_index = next(
        index
        for index, record in enumerate(records)
        if record.root_work_id == "electro-charged:same-frame"
    )
    assert scheduled_index < raw_index
    assert len(_reaction_results(assembled)) == 2


def test_electro_charged_gate_blocked_due_root_keeps_the_advanced_tick_cursor(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path, target_positions=(("target_1", 0.0), ("target_2", 13.0)))
    first = ElementalSubjectRef.target("target:target_1")
    second = ElementalSubjectRef.target("target:target_2")
    _apply_aura(assembled, first, Element.ELECTRO, "initial:first:electro")
    _apply_aura(assembled, second, Element.ELECTRO, "initial:second:electro")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:first"),
    )
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(
            Element.HYDRO,
            "electro-charged:second",
            target_ref="target_2",
        ),
    )

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 60)

    first_state = assembled.reaction_runtime.electro_charged_state_for(first)
    second_state = assembled.reaction_runtime.electro_charged_state_for(second)
    assert first_state is not None
    assert second_state is not None
    assert first_state.next_tick_frame == 120
    assert second_state.next_tick_frame == 120
    assert first_state.next_tick_index == 2
    assert second_state.next_tick_index == 2
    assert len(_reaction_results(assembled)) == 4
    roots = tuple(
        record
        for record in assembled.elemental_settlement_coordinator.records
        if record.batch_kind.value == "scheduled_reaction_root"
    )
    assert len(roots) == 2
    second_pulse = next(
        record
        for record in assembled.elemental_settlement_coordinator.records
        if record.batch_kind.value == "reaction_effect_group"
        and record.parent_work_id == roots[1].root_work_id
    )
    assert all(
        outcome.damage_outcome == "blocked_by_gate"
        for outcome in second_pulse.target_effect_outcomes
    )


def test_electro_charged_propagates_to_hydro_only_targets_without_creating_state(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path, target_positions=(("target_1", 0.0), ("target_2", 13.0)))
    first = ElementalSubjectRef.target("target:target_1")
    second = ElementalSubjectRef.target("target:target_2")
    _apply_aura(assembled, first, Element.ELECTRO, "initial:first:electro")
    _apply_aura(assembled, second, Element.HYDRO, "initial:second:hydro")

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:propagation"),
    )

    assert tuple(record.result.target_ref.entity_id for record in _reaction_records(assembled)) == (
        "target:target_1",
        "target:target_2",
    )
    assert assembled.reaction_runtime.electro_charged_state_for(second) is None
    hydro = assembled.aura_runtime.view(second).component_for(AuraKind.HYDRO)
    assert hydro is not None
    assert hydro.current_amount == AuraAmount("8/5")


def test_electro_charged_propagation_blocked_by_gate_does_not_consume_or_update_state(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path, target_positions=(("target_1", 0.0), ("target_2", 13.0)))
    first = ElementalSubjectRef.target("target:target_1")
    second = ElementalSubjectRef.target("target:target_2")
    _apply_aura(assembled, first, Element.ELECTRO, "initial:first:electro")
    _apply_aura(assembled, second, Element.ELECTRO, "initial:second:electro")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:first"),
    )
    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 1)

    state_before = assembled.reaction_runtime.electro_charged_state_for(first)
    aura_before = assembled.aura_runtime.view(first)
    assert state_before is not None
    hydro_before = aura_before.component_for(AuraKind.HYDRO)
    electro_before = aura_before.component_for(AuraKind.ELECTRO)
    assert hydro_before is not None
    assert electro_before is not None

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(
            Element.HYDRO,
            "electro-charged:second",
            frame=1,
            target_ref="target_2",
        ),
    )

    state_after = assembled.reaction_runtime.electro_charged_state_for(first)
    aura_after = assembled.aura_runtime.view(first)
    assert state_after == state_before
    assert aura_after.component_for(AuraKind.HYDRO) == hydro_before
    assert aura_after.component_for(AuraKind.ELECTRO) == electro_before
    assert len(_reaction_results(assembled)) == 2
    pulse_record = assembled.elemental_settlement_coordinator.records[-1]
    blocked = next(
        outcome for outcome in pulse_record.target_effect_outcomes if outcome.subject_ref == first
    )
    assert blocked.damage_outcome == "blocked_by_gate"


def test_electro_charged_propagation_takes_over_another_state_and_syncs_its_tick(
    tmp_path: Path,
):
    assembled = _assemble(
        tmp_path,
        target_positions=(("target_1", 0.0), ("target_2", 13.0)),
    )
    first = ElementalSubjectRef.target("target:target_1")
    second = ElementalSubjectRef.target("target:target_2")
    _apply_aura(assembled, first, Element.ELECTRO, "initial:first:electro")
    _apply_aura(assembled, second, Element.ELECTRO, "initial:second:electro")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:first"),
    )
    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 31)

    state_before = assembled.reaction_runtime.electro_charged_state_for(first)
    aura_before = assembled.aura_runtime.view(first)
    assert state_before is not None
    hydro_before = aura_before.component_for(AuraKind.HYDRO)
    electro_before = aura_before.component_for(AuraKind.ELECTRO)
    assert hydro_before is not None
    assert electro_before is not None

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(
            Element.HYDRO,
            "electro-charged:second",
            frame=31,
            target_ref="target_2",
        ),
    )

    state_after = assembled.reaction_runtime.electro_charged_state_for(first)
    second_state = assembled.reaction_runtime.electro_charged_state_for(second)
    aura_after = assembled.aura_runtime.view(first)
    assert state_after is not None
    assert second_state is not None
    assert state_after.instance_ref == state_before.instance_ref
    assert state_after.current_effect_owner != state_before.current_effect_owner
    assert state_after.current_effect_owner == second_state.current_effect_owner
    assert state_after.captured_scaling_basis.source_ref == second_state.current_effect_owner
    assert state_after.next_tick_frame == 91
    assert state_after.next_tick_index == state_before.next_tick_index
    assert state_after.revision == state_before.revision + 1
    hydro_after = aura_after.component_for(AuraKind.HYDRO)
    electro_after = aura_after.component_for(AuraKind.ELECTRO)
    assert hydro_after is not None
    assert electro_after is not None
    assert hydro_after.current_amount == hydro_before.current_amount - AuraAmount("2/5")
    assert electro_after.current_amount == electro_before.current_amount - AuraAmount("2/5")
    assert len(_reaction_results(assembled)) == 3


def test_electro_charged_pyro_combination_resolves_overloaded_then_vaporize(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    _apply_aura(assembled, target_ref, Element.ELECTRO, "initial:electro")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:first"),
    )

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.PYRO, "electro-charged:pyro"),
    )

    aura = assembled.aura_runtime.view(target_ref)
    hydro = aura.component_for(AuraKind.HYDRO)
    assert hydro is not None
    assert hydro.current_amount == AuraAmount("4/5")
    assert aura.component_for(AuraKind.ELECTRO) is None
    assert assembled.reaction_runtime.electro_charged_state_for(target_ref) is None
    assert len(_reaction_results(assembled)) == 2
    records = assembled.elemental_settlement_coordinator.records
    assert records[-2].reaction_occurrence_refs[-2:] == (
        "electro-charged:pyro:target:target_1:0:interaction:occurrence:0",
        "electro-charged:pyro:target:target_1:0:interaction:occurrence:1",
    )


def test_electro_charged_cryo_combination_suppresses_superconduct_damage_but_freezes(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    _apply_aura(assembled, target_ref, Element.ELECTRO, "initial:electro")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:first"),
    )

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(
            Element.CRYO,
            "electro-charged:cryo",
            elemental_amount=AuraAmount(3),
            elemental_strength=AuraStrength.SUPER_STRONG,
        ),
    )

    assert assembled.reaction_runtime.electro_charged_state_for(target_ref) is None
    assert assembled.reaction_runtime.frozen_state_for(target_ref) is not None
    assert len(_reaction_results(assembled)) == 1
    hidden_cryo = assembled.aura_runtime.view(target_ref).component_for(AuraKind.CRYO)
    assert hidden_cryo is not None
    assert hidden_cryo.current_amount == AuraAmount("3/5")
    superconduct_event = next(
        event
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.REACTION_OCCURRED
        and isinstance(event.payload, ReactionOccurredPayload)
        and event.payload.occurrence.reaction_key == "reaction.superconduct"
    )
    superconduct_payload = superconduct_event.payload.to_dict()
    effect_groups = cast(tuple[dict[str, object], ...], superconduct_payload["effect_groups"])
    assert effect_groups[0]["suppressed_effect_refs"]


def test_electro_charged_lifecycle_notification_removes_future_periodic_work(tmp_path: Path):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    _apply_aura(assembled, target_ref, Element.ELECTRO, "initial:electro")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:first"),
    )

    assert assembled.elemental_settlement_coordinator.end_reaction_subject_lifecycle(
        assembled.context,
        subject_ref=target_ref,
        frame=1,
    )
    assert assembled.reaction_runtime.electro_charged_state_for(target_ref) is None

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 60)

    assert len(_reaction_results(assembled)) == 1
    assert not any(
        record.batch_kind.value == "scheduled_reaction_root"
        for record in assembled.elemental_settlement_coordinator.records
    )


def test_electro_charged_due_root_removes_state_when_primary_loses_damage_capability(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    _apply_aura(assembled, target_ref, Element.ELECTRO, "initial:electro")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _aura_request(Element.HYDRO, "electro-charged:first"),
    )
    assembled.elemental_settlement_coordinator.target_eligibility_port = _NoDamageCapabilityPort()

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 60)

    assert assembled.reaction_runtime.electro_charged_state_for(target_ref) is None
    assert len(_reaction_results(assembled)) == 1


def _reaction_records(assembled):
    return tuple(
        record
        for record in assembled.damage_handler.records
        if record.result.damage_type is DamageType.TRANSFORMATIVE_REACTION
    )


def _reaction_results(assembled):
    return tuple(record.result for record in _reaction_records(assembled))


class _NoDamageCapabilityPort:
    def evaluate(self, context, *, entity, distance_xz: float):
        result = DefaultReactionTargetEligibilityPort().evaluate(
            context,
            entity=entity,
            distance_xz=distance_xz,
        )
        return replace(result, capabilities=frozenset())


def _apply_aura(
    assembled,
    target_ref: ElementalSubjectRef,
    element: Element,
    request_id: str,
) -> None:
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            request_id,
            f"{request_id}:application",
            f"{request_id}:impact",
            0,
            0,
            ElementalSourceRef("initial"),
            target_ref,
            element,
            AuraStrength.STRONG,
        )
    )


def _aura_request(
    element: Element,
    request_id: str,
    *,
    frame: int = 0,
    elemental_amount: AuraAmount | None = None,
    elemental_strength: AuraStrength = AuraStrength.STRONG,
    target_ref: str = "target_1",
) -> ImpactRequest:
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.APPLY_AURA,
        impact_key="golden.electro_charged.application",
        owner_slot=1,
        request_id=request_id,
        target_refs=(target_ref,),
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref=request_id,
            element=element,
            elemental_strength=elemental_strength,
            elemental_amount=AuraAmount(2) if elemental_amount is None else elemental_amount,
        ),
    )


def _assemble(
    tmp_path: Path,
    *,
    target_positions: tuple[tuple[str, float], ...] = (("target_1", 0.0),),
):
    asset_db = tmp_path / "assets.db"
    write_minimal_static_asset_database(asset_db)
    return SimulationAssembler(
        SQLiteAssetRepository(asset_db),
    ).assemble(
        SimulationConfig.from_mapping(
            {
                "schema_version": 1,
                "kind": "simulation_config",
                "meta": {"name": "electro charged golden", "description": ""},
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
                            "id": target_id,
                            "level": 90,
                            "position": {"x": position, "y": 0, "z": 0},
                            "resistance": {},
                        }
                        for target_id, position in target_positions
                    ]
                },
                "input_trace": [],
                "rules": {"enabled": []},
                "run_options": {"max_frames": 120},
            }
        )
    )
