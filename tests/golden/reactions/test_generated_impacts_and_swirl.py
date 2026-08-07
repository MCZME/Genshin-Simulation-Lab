from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.config import SimulationConfig
from genshin_sim.core.coordination.elemental_reaction import (
    DefaultReactionTargetEligibilityPort,
    ElementalInteractionBatchRecord,
    ElementalInteractionCoordinator,
    ElementalSettlementCoordinator,
    ElementalStateFrameCoordinator,
    ReactionTargetCapability,
    ReactionTargetEligibility,
    ReactionTargetRelation,
    SimultaneousElementApplicationPolicyError,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.events import (
    ElementalInteractionResolvedPayload,
    EventType,
    ReactionOccurredPayload,
)
from genshin_sim.core.impacts import (
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationProfile,
    AuraApplicationProfileRegistry,
    AuraApplicationRequest,
    AuraComponent,
    AuraContribution,
    AuraContributionRef,
    AuraDecayProfilePolicy,
    AuraInstanceRef,
    AuraLossPolicy,
    AuraStrength,
    AuraView,
)
from genshin_sim.core.systems.damage import (
    DamageProfile,
    DamageProfileRegistry,
    DamageReactionCapability,
    DamageRequestHandler,
    DamageType,
    TransformativeReactionInput,
)
from genshin_sim.core.systems.reaction import (
    ReactionEvaluationRequest,
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
    ReactionGeneratedImpactDamageComponent,
    ReactionGeneratedImpactProvenance,
    ReactionRegistry,
    ReactionRuntime,
    SwirlEmissionSelection,
    TransformativeSourceObservation,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import (
    SwirlGeneratedImpactDamageInputAdapter,
    swirl_aura_application_profile,
    swirl_definition,
)
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    write_minimal_static_asset_database,
)

ROOT_WORK_ID = "root:test-generated-impact"
SOURCE = ElementalSourceRef("character:slot_1", ROOT_WORK_ID)
ANCHOR = ElementalSubjectRef.target("target:target_1")
TARGET = ElementalSubjectRef.target("target:target_2")


def test_generated_electro_hydro_batch_freezes_targets_and_commits_common_aura_plan(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    coordinator.aura_application_profile_registry = _profile_registry()

    coordinator._settle_follow_up_groups(  # noqa: SLF001 - exercise the queued contract.
        assembled.context,
        _root_record(_generated_batch()),
    )

    anchor_aura = assembled.aura_runtime.view(ANCHOR)
    target_aura = assembled.aura_runtime.view(TARGET)
    hydro = target_aura.component_for(AuraKind.HYDRO)
    electro = target_aura.component_for(AuraKind.ELECTRO)
    assert not anchor_aura.components
    assert hydro is not None
    assert electro is not None
    assert hydro.current_amount == AuraAmount("44/25")
    assert electro.current_amount == AuraAmount("44/25")
    assert hydro.contributions[0].contributor_ref == SOURCE
    assert electro.contributions[0].contributor_ref == SOURCE
    assert not assembled.aura_runtime.view(ElementalSubjectRef.target("target:target_3")).components
    assert not any(
        event.event_type is EventType.REACTION_OCCURRED
        for event in assembled.context.events.frame_events
    )

    record = coordinator.records[-1]
    assert record.batch_kind.value == "reaction_generated_impact_batch"
    assert record.settlement_round == 1
    assert record.emission_batch_ref == "emission:test-electro-hydro"
    assert record.generated_impact_refs == ("impact:electro", "impact:hydro")
    assert record.simultaneous_application_policy_keys == (
        "simultaneous_application.no_aura_electro_hydro_coexistence",
    )
    assert record.captured_source_observation_ref == "observation:test-generated-impact"
    target_outcome = next(
        item for item in record.target_effect_outcomes if item.subject_ref == TARGET
    )
    assert target_outcome.aura_outcome == "applied"

    resolved = next(
        event
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.ELEMENTAL_INTERACTION_RESOLVED
        and isinstance(event.payload, ElementalInteractionResolvedPayload)
        and event.payload.record.batch_id == record.batch_id
    )
    payload = resolved.payload.to_dict()
    target_payload = next(
        item
        for item in cast(list[dict[str, object]], payload["target_effect_outcomes"])
        if item["subject_ref"] == {"kind": "target", "entity_id": "target:target_2"}
    )
    assert payload["generated_impact_refs"] == ["impact:electro", "impact:hydro"]
    assert target_payload["aura_outcome"] == "applied"


def test_unsupported_generated_batch_preserves_the_entire_uncommitted_aura_plan(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    coordinator.aura_application_profile_registry = _profile_registry()
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            request_id="aura:existing-pyro",
            application_id="aura:existing-pyro:application",
            impact_ref="impact:existing-pyro",
            frame=0,
            order=0,
            source_ref=ElementalSourceRef("test:existing-pyro"),
            target_ref=TARGET,
            element=Element.PYRO,
            base_strength=AuraStrength.WEAK,
        )
    )

    with pytest.raises(SimultaneousElementApplicationPolicyError):
        coordinator._settle_follow_up_groups(  # noqa: SLF001 - exercise the queued contract.
            assembled.context,
            _root_record(_generated_batch()),
        )

    target_aura = assembled.aura_runtime.view(TARGET)
    assert target_aura.component_for(AuraKind.PYRO) is not None
    assert target_aura.component_for(AuraKind.HYDRO) is None
    assert target_aura.component_for(AuraKind.ELECTRO) is None
    assert not coordinator.records


def test_generated_single_element_uses_existing_reaction_planner_and_preserves_source(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    coordinator.aura_application_profile_registry = _profile_registry()
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            request_id="aura:existing-pyro-for-generated-hydro",
            application_id="aura:existing-pyro-for-generated-hydro:application",
            impact_ref="impact:existing-pyro-for-generated-hydro",
            frame=0,
            order=0,
            source_ref=ElementalSourceRef("test:existing-pyro"),
            target_ref=TARGET,
            element=Element.PYRO,
            base_strength=AuraStrength.WEAK,
        )
    )

    coordinator._settle_follow_up_groups(  # noqa: SLF001 - exercise the queued contract.
        assembled.context,
        _root_record(_single_hydro_batch()),
    )

    target_aura = assembled.aura_runtime.view(TARGET)
    assert target_aura.component_for(AuraKind.PYRO) is None
    assert target_aura.component_for(AuraKind.HYDRO) is None

    record = coordinator.records[-1]
    assert record.generated_impact_refs == ("impact:hydro",)
    assert len(record.reaction_occurrence_refs) == 1
    assert record.reaction_decision_steps[0].selected_candidate_keys == ("reaction.vaporize",)
    target_outcome = next(
        item for item in record.target_effect_outcomes if item.subject_ref == TARGET
    )
    assert target_outcome.aura_outcome == "reaction_resolved"

    occurred = next(
        event
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.REACTION_OCCURRED
    )
    assert isinstance(occurred.payload, ReactionOccurredPayload)
    assert occurred.payload.occurrence.source_ref == SOURCE
    assert occurred.payload.occurrence.subject_ref == TARGET


def test_generated_single_element_enqueues_new_effect_group_in_later_round(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    coordinator.aura_application_profile_registry = _profile_registry()
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            request_id="aura:existing-hydro-for-generated-electro",
            application_id="aura:existing-hydro-for-generated-electro:application",
            impact_ref="impact:existing-hydro-for-generated-electro",
            frame=0,
            order=0,
            source_ref=ElementalSourceRef("test:existing-hydro"),
            target_ref=TARGET,
            element=Element.HYDRO,
            base_strength=AuraStrength.WEAK,
        )
    )

    coordinator._settle_follow_up_groups(  # noqa: SLF001 - exercise the queued contract.
        assembled.context,
        _root_record(_single_electro_batch()),
    )

    state = assembled.reaction_runtime.electro_charged_state_for(TARGET)
    assert state is not None
    generated_record, effect_record = coordinator.records[-2:]
    assert generated_record.settlement_round == 1
    assert generated_record.follow_up_work_ids
    assert effect_record.batch_kind.value == "reaction_effect_group"
    assert effect_record.settlement_round == 2
    assert effect_record.parent_work_id == generated_record.work_ids[0]


def test_generated_damage_component_is_gated_without_blocking_element_application(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    coordinator.aura_application_profile_registry = _profile_registry()
    coordinator.generated_impact_damage_input_adapter = _TestDamageInputAdapter(2.0)

    first_root = "root:test-generated-damage:first"
    coordinator._settle_follow_up_groups(  # noqa: SLF001 - exercise the queued contract.
        assembled.context,
        _root_record_for(first_root, _single_electro_damage_batch(first_root)),
    )

    first_record = coordinator.records[-1]
    first_outcome = next(
        item for item in first_record.target_effect_outcomes if item.subject_ref == TARGET
    )
    assert first_outcome.aura_outcome == "applied"
    assert first_outcome.damage_outcome == "applied"
    assert first_outcome.gate_resolution_ref is not None
    assert first_record.damage_request_ids
    first_damage_count = len(assembled.damage_handler.records)

    second_root = "root:test-generated-damage:second"
    coordinator._settle_follow_up_groups(  # noqa: SLF001 - exercise the queued contract.
        assembled.context,
        _root_record_for(second_root, _single_electro_damage_batch(second_root)),
    )

    second_record = coordinator.records[-1]
    second_outcome = next(
        item for item in second_record.target_effect_outcomes if item.subject_ref == TARGET
    )
    assert second_outcome.aura_outcome == "applied"
    assert second_outcome.damage_outcome == "blocked_by_gate"
    assert second_record.damage_request_ids == ()
    assert len(assembled.damage_handler.records) == first_damage_count


def test_generated_damage_component_passes_captured_secondary_amplification_input(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    coordinator.aura_application_profile_registry = _profile_registry()
    coordinator.generated_impact_damage_input_adapter = _TestDamageInputAdapter(0.6)
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            request_id="aura:existing-pyro-for-generated-secondary",
            application_id="aura:existing-pyro-for-generated-secondary:application",
            impact_ref="impact:existing-pyro-for-generated-secondary",
            frame=0,
            order=0,
            source_ref=ElementalSourceRef("test:existing-pyro"),
            target_ref=TARGET,
            element=Element.PYRO,
            base_strength=AuraStrength.WEAK,
        )
    )
    handler = DamageRequestHandler(
        assembled.damage_handler.resolver,
        profile_registry=_secondary_capable_profile_registry(),
    )
    coordinator.damage_handler = handler

    root_work_id = "root:test-generated-secondary"
    coordinator._settle_follow_up_groups(  # noqa: SLF001 - exercise the queued contract.
        assembled.context,
        _root_record_for(
            root_work_id,
            _single_hydro_secondary_damage_batch(root_work_id),
        ),
    )

    record = coordinator.records[-1]
    assert record.reaction_occurrence_refs
    damage_record = handler.records[0]
    secondary = damage_record.damage_request.secondary_amplifying_reaction
    assert secondary is not None
    assert secondary.target_impact_ref == "impact:root:test-generated-secondary:hydro"
    assert secondary.captured_elemental_mastery == 100.0
    assert damage_record.result.secondary_amplifying_resolution is not None


@pytest.mark.parametrize(
    ("aura_kind", "output_element", "damage_element"),
    (
        (AuraKind.PYRO, Element.PYRO, Element.PYRO),
        (AuraKind.ELECTRO, Element.ELECTRO, Element.ELECTRO),
        (AuraKind.CRYO, Element.CRYO, Element.CRYO),
    ),
)
def test_swirl_non_hydro_emission_applies_damage_and_regular_aura_to_six_meter_targets(
    tmp_path: Path,
    aura_kind: AuraKind,
    output_element: Element,
    damage_element: Element,
):
    assembled = _assemble(tmp_path)
    coordinator, handler = _swirl_settlement_coordinator(assembled)
    root_work_id = f"root:swirl-range:{aura_kind.value}"
    batch = _swirl_batch(root_work_id, aura_kind)

    coordinator._settle_follow_up_groups(  # noqa: SLF001 - exercise the queued contract.
        assembled.context,
        _root_record_for(root_work_id, batch),
    )

    target_aura = assembled.aura_runtime.view(TARGET).component_for(
        {
            Element.PYRO: AuraKind.PYRO,
            Element.ELECTRO: AuraKind.ELECTRO,
            Element.CRYO: AuraKind.CRYO,
        }[output_element]
    )
    assert target_aura is not None
    assert target_aura.current_amount == AuraAmount("44/25")
    assert not assembled.aura_runtime.view(ElementalSubjectRef.target("target:target_3")).components
    assert len(handler.records) == 1
    damage = handler.records[0].result
    assert damage.damage_type is DamageType.TRANSFORMATIVE_REACTION
    assert damage.final_damage == pytest.approx(868.1118)
    assert damage.element is damage_element
    assert damage.reaction_details is not None
    assert damage.reaction_details.base_multiplier == 0.6
    outcome = next(
        item
        for item in coordinator.records[-1].target_effect_outcomes
        if item.subject_ref == TARGET
    )
    assert outcome.aura_outcome == "applied"
    assert outcome.damage_outcome == "applied"


def test_swirl_hydro_emission_applies_aura_without_range_damage(tmp_path: Path):
    assembled = _assemble(tmp_path)
    coordinator, handler = _swirl_settlement_coordinator(assembled)
    root_work_id = "root:swirl-range:hydro"

    coordinator._settle_follow_up_groups(  # noqa: SLF001 - exercise the queued contract.
        assembled.context,
        _root_record_for(root_work_id, _swirl_batch(root_work_id, AuraKind.HYDRO)),
    )

    hydro = assembled.aura_runtime.view(TARGET).component_for(AuraKind.HYDRO)
    assert hydro is not None
    assert hydro.current_amount == AuraAmount("44/25")
    assert not handler.records
    outcome = next(
        item
        for item in coordinator.records[-1].target_effect_outcomes
        if item.subject_ref == TARGET
    )
    assert outcome.aura_outcome == "applied"
    assert outcome.damage_outcome is None


def test_swirl_center_and_range_damage_use_the_mechanism_declared_multiplier(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator, handler = _swirl_settlement_coordinator(assembled)
    root_work_id = "root:swirl-center-and-range"
    resolution = _swirl_resolution(root_work_id, AuraKind.PYRO)
    assert resolution.occurrence is not None

    coordinator._settle_follow_up_groups(  # noqa: SLF001 - exercise the queued contract.
        assembled.context,
        _root_record_for(
            root_work_id,
            resolution.generated_impact_batches[0],
            reaction_effect_groups=resolution.occurrence.effect_groups,
        ),
    )

    results_by_target = {
        record.damage_request.target_ref.entity_id: record.result for record in handler.records
    }
    assert set(results_by_target) == {"target:target_1", "target:target_2"}
    assert all(
        result.final_damage == pytest.approx(868.1118) for result in results_by_target.values()
    )
    assert all(result.reaction_details is not None for result in results_by_target.values())
    assert all(
        result.reaction_details.base_multiplier == 0.6
        for result in results_by_target.values()
        if result.reaction_details is not None
    )


def test_swirl_test_runtime_settles_the_real_anemo_root_through_center_and_range(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    handler = assembled.damage_handler
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            request_id="aura:swirl-root:pyro",
            application_id="aura:swirl-root:pyro:application",
            impact_ref="impact:swirl-root:pyro",
            frame=0,
            order=0,
            source_ref=ElementalSourceRef("test:initial-pyro"),
            target_ref=ANCHOR,
            element=Element.PYRO,
            base_strength=AuraStrength.WEAK,
        )
    )

    root_record = coordinator.settle_aura_impact(
        assembled.context,
        ImpactRequest(
            frame=0,
            kind=ImpactKind.APPLY_AURA,
            impact_key="test.swirl.root.anemo",
            owner_slot=1,
            request_id="root:swirl:anemo",
            target_refs=("target_1",),
            elemental_application_spec=ElementalApplicationSpec(
                impact_ref="impact:swirl-root:anemo",
                element=Element.ANEMO,
                elemental_strength=AuraStrength.WEAK,
                elemental_amount=AuraAmount.one(),
            ),
        ),
    )

    pyro_on_anchor = assembled.aura_runtime.view(ANCHOR).component_for(AuraKind.PYRO)
    pyro_on_range_target = assembled.aura_runtime.view(TARGET).component_for(AuraKind.PYRO)
    assert root_record.reaction_occurrence_refs
    assert root_record.reaction_effect_groups
    assert root_record.generated_impact_batches
    assert pyro_on_anchor is not None
    assert pyro_on_anchor.current_amount == AuraAmount("0.3")
    assert pyro_on_range_target is not None
    assert pyro_on_range_target.current_amount == AuraAmount("44/25")
    assert len(handler.records) == 2
    assert {record.damage_request.target_ref.entity_id for record in handler.records} == {
        "target:target_1",
        "target:target_2",
    }
    assert all(record.result.final_damage == pytest.approx(868.1118) for record in handler.records)


def test_production_swirl_electro_hydro_uses_shared_emission_and_simultaneous_coexistence(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    _apply_lossless_aura(
        assembled,
        target_ref=ANCHOR,
        request_ref="aura:double-swirl:electro",
        element=Element.ELECTRO,
        amount=AuraAmount("0.4"),
    )
    _apply_lossless_aura(
        assembled,
        target_ref=ANCHOR,
        request_ref="aura:double-swirl:hydro",
        element=Element.HYDRO,
        amount=AuraAmount("0.4"),
    )

    root_record = coordinator.settle_aura_impact(
        assembled.context,
        _anemo_root_request("root:double-swirl:electro-hydro"),
    )

    batch = root_record.generated_impact_batches[0]
    target_view = assembled.aura_runtime.view(TARGET)
    target_electro = target_view.component_for(AuraKind.ELECTRO)
    target_hydro = target_view.component_for(AuraKind.HYDRO)
    assert len(root_record.reaction_occurrence_refs) == 2
    assert [impact.element for impact in batch.impacts] == [Element.ELECTRO, Element.HYDRO]
    assert {impact.elemental_amount for impact in batch.impacts} == {AuraAmount("1.2")}
    assert target_electro is not None
    assert target_hydro is not None
    assert target_electro.current_amount == AuraAmount("0.96")
    assert target_hydro.current_amount == AuraAmount("0.96")
    emission_record = next(
        record
        for record in coordinator.records
        if record.emission_batch_ref == batch.emission_batch_ref
    )
    assert emission_record.simultaneous_application_policy_keys == (
        "simultaneous_application.no_aura_electro_hydro_coexistence",
    )
    assert len(assembled.damage_handler.records) == 3


def test_double_swirl_damage_does_not_require_aura_capability(tmp_path: Path):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    coordinator.target_eligibility_port = _DamageOnlyTargetEligibilityPort(TARGET)
    _apply_lossless_aura(
        assembled,
        target_ref=ANCHOR,
        request_ref="aura:damage-only-double-swirl:electro",
        element=Element.ELECTRO,
        amount=AuraAmount("0.4"),
    )
    _apply_lossless_aura(
        assembled,
        target_ref=ANCHOR,
        request_ref="aura:damage-only-double-swirl:hydro",
        element=Element.HYDRO,
        amount=AuraAmount("0.4"),
    )

    root_record = coordinator.settle_aura_impact(
        assembled.context,
        _anemo_root_request("root:damage-only-double-swirl"),
    )

    batch = root_record.generated_impact_batches[0]
    emission_record = next(
        record
        for record in coordinator.records
        if record.emission_batch_ref == batch.emission_batch_ref
    )
    outcome = next(
        item for item in emission_record.target_effect_outcomes if item.subject_ref == TARGET
    )
    assert outcome.damage_outcome == "applied"
    assert outcome.aura_outcome == "unsupported_aura_capability"
    assert not assembled.aura_runtime.view(TARGET).components
    assert any(
        record.damage_request.target_ref.entity_id == TARGET.entity_id
        for record in assembled.damage_handler.records
    )


def test_production_swirl_frozen_hydro_creates_frozen_range_targets_atomically(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    coordinator.settle_aura_impact(
        assembled.context,
        _elemental_root_request("root:freeze:hydro", Element.HYDRO),
    )
    coordinator.settle_aura_impact(
        assembled.context,
        _elemental_root_request("root:freeze:cryo", Element.CRYO),
    )
    _apply_lossless_aura(
        assembled,
        target_ref=ANCHOR,
        request_ref="aura:double-swirl:hidden-hydro",
        element=Element.HYDRO,
        amount=AuraAmount("0.4"),
    )

    root_record = coordinator.settle_aura_impact(
        assembled.context,
        _anemo_root_request("root:double-swirl:frozen-hydro", frame=1),
    )

    batch = root_record.generated_impact_batches[0]
    target_view = assembled.aura_runtime.view(TARGET)
    assert [impact.element for impact in batch.impacts] == [Element.HYDRO, Element.CRYO]
    assert target_view.component_for(AuraKind.FROZEN) is not None
    assert assembled.reaction_runtime.frozen_state_for(TARGET) is not None
    emission_record = next(
        record
        for record in coordinator.records
        if record.emission_batch_ref == batch.emission_batch_ref
    )
    assert emission_record.simultaneous_application_policy_keys == (
        "simultaneous_application.no_aura_hydro_cryo_frozen",
    )
    assert len(assembled.damage_handler.records) == 3


def test_production_swirl_hidden_cryo_consumes_frozen_link_with_one_cryo_emission(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    coordinator = assembled.elemental_settlement_coordinator
    coordinator.settle_aura_impact(
        assembled.context,
        _elemental_root_request("root:hidden-cryo:freeze-hydro", Element.HYDRO),
    )
    coordinator.settle_aura_impact(
        assembled.context,
        _elemental_root_request("root:hidden-cryo:freeze-cryo", Element.CRYO),
    )
    _apply_lossless_aura(
        assembled,
        target_ref=ANCHOR,
        request_ref="aura:hidden-cryo",
        element=Element.CRYO,
        amount=AuraAmount("0.4"),
    )

    root_record = coordinator.settle_aura_impact(
        assembled.context,
        _anemo_root_request(
            "root:double-swirl:hidden-cryo",
            frame=1,
            amount=AuraAmount(4),
        ),
    )

    batch = root_record.generated_impact_batches[0]
    assert root_record.reaction_occurrence_refs == (
        "root:double-swirl:hidden-cryo:target:target_1:0:interaction:occurrence:0",
    )
    assert len(root_record.reaction_decision_steps) == 2
    assert root_record.reaction_decision_steps[1].occurrence_refs == ()
    assert [impact.element for impact in batch.impacts] == [Element.CRYO]
    assert assembled.aura_runtime.view(ANCHOR).component_for(AuraKind.FROZEN) is None
    assert assembled.reaction_runtime.frozen_state_for(ANCHOR) is None
    assert assembled.aura_runtime.view(TARGET).component_for(AuraKind.CRYO) is not None
    assert len(assembled.damage_handler.records) == 2


def _apply_lossless_aura(
    assembled,
    *,
    target_ref: ElementalSubjectRef,
    request_ref: str,
    element: Element,
    amount: AuraAmount,
) -> None:
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            request_id=request_ref,
            application_id=f"{request_ref}:application",
            impact_ref=f"{request_ref}:impact",
            frame=0,
            order=0,
            source_ref=ElementalSourceRef("test:initial-aura"),
            target_ref=target_ref,
            element=element,
            base_strength=AuraStrength.WEAK,
            loss_policy=AuraLossPolicy.LOSSLESS,
            effective_raw_amount=amount,
        )
    )


def _anemo_root_request(
    request_id: str,
    *,
    frame: int = 0,
    amount: AuraAmount | None = None,
) -> ImpactRequest:
    return _elemental_root_request(request_id, Element.ANEMO, frame=frame, amount=amount)


def _elemental_root_request(
    request_id: str,
    element: Element,
    *,
    frame: int = 0,
    amount: AuraAmount | None = None,
) -> ImpactRequest:
    resolved_amount = AuraAmount.one() if amount is None else amount
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.APPLY_AURA,
        impact_key=f"test.generated-impact.{element.value}",
        owner_slot=1,
        request_id=request_id,
        target_refs=("target_1",),
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref=f"impact:{request_id}",
            element=element,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=resolved_amount,
        ),
    )


def _generated_batch() -> ReactionGeneratedImpactBatch:
    return ReactionGeneratedImpactBatch(
        emission_batch_ref="emission:test-electro-hydro",
        parent_root_work_ref=ROOT_WORK_ID,
        parent_occurrence_refs=("occurrence:test-generated-impact",),
        settlement_round=1,
        target_selection=SwirlEmissionSelection("selection:test-generated-impact", ANCHOR),
        source_ref=SOURCE,
        captured_source_observation=TransformativeSourceObservation(
            source_ref=SOURCE,
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=90,
            elemental_mastery=0.0,
            level_multiplier_table_key="character",
            level_multiplier=1446.853,
            source_observation_ref="observation:test-generated-impact",
            source_owner_slot=1,
        ),
        impacts=(
            _impact("impact:electro", 0, Element.ELECTRO),
            _impact("impact:hydro", 1, Element.HYDRO),
        ),
    )


def _single_hydro_batch() -> ReactionGeneratedImpactBatch:
    return ReactionGeneratedImpactBatch(
        emission_batch_ref="emission:test-hydro",
        parent_root_work_ref=ROOT_WORK_ID,
        parent_occurrence_refs=("occurrence:test-generated-impact",),
        settlement_round=1,
        target_selection=SwirlEmissionSelection("selection:test-generated-impact", ANCHOR),
        source_ref=SOURCE,
        captured_source_observation=TransformativeSourceObservation(
            source_ref=SOURCE,
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=90,
            elemental_mastery=0.0,
            level_multiplier_table_key="character",
            level_multiplier=1446.853,
            source_observation_ref="observation:test-generated-impact",
            source_owner_slot=1,
        ),
        impacts=(_impact("impact:hydro", 0, Element.HYDRO),),
    )


def _single_electro_batch() -> ReactionGeneratedImpactBatch:
    return ReactionGeneratedImpactBatch(
        emission_batch_ref="emission:test-electro",
        parent_root_work_ref=ROOT_WORK_ID,
        parent_occurrence_refs=("occurrence:test-generated-impact",),
        settlement_round=1,
        target_selection=SwirlEmissionSelection("selection:test-generated-impact", ANCHOR),
        source_ref=SOURCE,
        captured_source_observation=TransformativeSourceObservation(
            source_ref=SOURCE,
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=90,
            elemental_mastery=0.0,
            level_multiplier_table_key="character",
            level_multiplier=1446.853,
            source_observation_ref="observation:test-generated-impact",
            source_owner_slot=1,
        ),
        impacts=(_impact("impact:electro", 0, Element.ELECTRO),),
    )


def _single_electro_damage_batch(root_work_id: str) -> ReactionGeneratedImpactBatch:
    source = ElementalSourceRef("character:slot_1", root_work_id)
    return ReactionGeneratedImpactBatch(
        emission_batch_ref=f"emission:{root_work_id}",
        parent_root_work_ref=root_work_id,
        parent_occurrence_refs=(f"occurrence:{root_work_id}",),
        settlement_round=1,
        target_selection=SwirlEmissionSelection("selection:test-generated-impact", ANCHOR),
        source_ref=source,
        captured_source_observation=TransformativeSourceObservation(
            source_ref=source,
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=90,
            elemental_mastery=0.0,
            level_multiplier_table_key="character",
            level_multiplier=1446.853,
            source_observation_ref=f"observation:{root_work_id}",
            source_owner_slot=1,
        ),
        impacts=(
            ReactionGeneratedImpact(
                generated_impact_ref=f"impact:{root_work_id}:electro",
                emission_order=0,
                element=Element.ELECTRO,
                elemental_amount=AuraAmount("11/5"),
                aura_application_profile_key="aura_application_profile.test.generated",
                provenance=ReactionGeneratedImpactProvenance(
                    provenance_ref=f"provenance:{root_work_id}",
                    parent_occurrence_ref=f"occurrence:{root_work_id}",
                    reaction_profile_key="reaction_profile.test.generated",
                ),
                damage_component=ReactionGeneratedImpactDamageComponent(
                    main_attack_tag="reaction.electro_charged",
                    damage_profile_key="damage_profile.reaction.electro_charged",
                    damage_element=Element.ELECTRO,
                    gate_definition_key="reaction_gate.electro_charged.damage",
                    damage_kind_key="reaction_damage.electro_charged",
                ),
            ),
        ),
    )


def _single_hydro_secondary_damage_batch(root_work_id: str) -> ReactionGeneratedImpactBatch:
    source = ElementalSourceRef("character:slot_1", root_work_id)
    return ReactionGeneratedImpactBatch(
        emission_batch_ref=f"emission:{root_work_id}",
        parent_root_work_ref=root_work_id,
        parent_occurrence_refs=(f"occurrence:{root_work_id}",),
        settlement_round=1,
        target_selection=SwirlEmissionSelection("selection:test-generated-impact", ANCHOR),
        source_ref=source,
        captured_source_observation=TransformativeSourceObservation(
            source_ref=source,
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=90,
            elemental_mastery=100.0,
            level_multiplier_table_key="character",
            level_multiplier=1446.853,
            source_observation_ref=f"observation:{root_work_id}",
            source_owner_slot=1,
        ),
        impacts=(
            ReactionGeneratedImpact(
                generated_impact_ref=f"impact:{root_work_id}:hydro",
                emission_order=0,
                element=Element.HYDRO,
                elemental_amount=AuraAmount("11/5"),
                aura_application_profile_key="aura_application_profile.test.generated",
                provenance=ReactionGeneratedImpactProvenance(
                    provenance_ref=f"provenance:{root_work_id}",
                    parent_occurrence_ref=f"occurrence:{root_work_id}",
                    reaction_profile_key="reaction_profile.test.generated",
                ),
                damage_component=ReactionGeneratedImpactDamageComponent(
                    main_attack_tag="test.generated.swirl",
                    damage_profile_key="damage_profile.test.generated_swirl",
                    damage_element=Element.HYDRO,
                    gate_definition_key="reaction_gate.electro_charged.damage",
                    damage_kind_key="reaction_damage.electro_charged",
                ),
            ),
        ),
    )


def _impact(
    generated_impact_ref: str,
    emission_order: int,
    element: Element,
) -> ReactionGeneratedImpact:
    return ReactionGeneratedImpact(
        generated_impact_ref=generated_impact_ref,
        emission_order=emission_order,
        element=element,
        elemental_amount=AuraAmount("11/5"),
        aura_application_profile_key="aura_application_profile.test.generated",
        provenance=ReactionGeneratedImpactProvenance(
            provenance_ref=f"provenance:{generated_impact_ref}",
            parent_occurrence_ref="occurrence:test-generated-impact",
            reaction_profile_key="reaction_profile.test.generated",
        ),
    )


def _root_record(batch: ReactionGeneratedImpactBatch) -> ElementalInteractionBatchRecord:
    return _root_record_for(ROOT_WORK_ID, batch)


def _root_record_for(
    root_work_id: str,
    batch: ReactionGeneratedImpactBatch,
    *,
    reaction_effect_groups=(),
) -> ElementalInteractionBatchRecord:
    return ElementalInteractionBatchRecord(
        batch_id=root_work_id,
        root_work_id=root_work_id,
        frame=0,
        settlement_round=0,
        work_ids=(root_work_id,),
        icd_request_ids=(),
        aura_transition_interaction_ids=(),
        reaction_occurrence_refs=batch.parent_occurrence_refs,
        damage_request_ids=(),
        reaction_effect_groups=reaction_effect_groups,
        generated_impact_batches=(batch,),
    )


class _TestDamageInputAdapter:
    def __init__(self, base_multiplier: float) -> None:
        self.base_multiplier = base_multiplier

    def transformative_input(
        self,
        *,
        batch: ReactionGeneratedImpactBatch,
        impact: ReactionGeneratedImpact,
    ) -> TransformativeReactionInput:
        source = batch.captured_source_observation
        occurrence_ref = impact.provenance.parent_occurrence_ref
        if occurrence_ref is None:
            raise ValueError("扩散派生 Impact 必须具有 occurrence cause")
        return TransformativeReactionInput(
            occurrence_ref=occurrence_ref,
            reaction_profile_key=impact.provenance.reaction_profile_key,
            source_kind=source.source_kind,
            source_level=source.source_level,
            level_multiplier_table_key=source.level_multiplier_table_key,
            level_multiplier=source.level_multiplier,
            elemental_mastery=source.elemental_mastery,
            mastery_bonus=(16 * source.elemental_mastery / (source.elemental_mastery + 2000)),
            reaction_bonus=0.0,
            base_multiplier=self.base_multiplier,
        )


class _DamageOnlyTargetEligibilityPort:
    def __init__(self, damage_only_subject_ref: ElementalSubjectRef) -> None:
        self.damage_only_subject_ref = damage_only_subject_ref
        self.default = DefaultReactionTargetEligibilityPort()

    def evaluate(self, context, *, entity, distance_xz: float) -> ReactionTargetEligibility:
        eligibility = self.default.evaluate(
            context,
            entity=entity,
            distance_xz=distance_xz,
        )
        if eligibility.subject_ref != self.damage_only_subject_ref:
            return eligibility
        return ReactionTargetEligibility(
            subject_ref=eligibility.subject_ref,
            spatial_entity_id=eligibility.spatial_entity_id,
            distance_xz=eligibility.distance_xz,
            relation=ReactionTargetRelation.HOSTILE,
            capabilities=frozenset({ReactionTargetCapability.DAMAGE}),
        )


def _secondary_capable_profile_registry():
    return DamageProfileRegistry(
        (
            DamageProfile(
                "damage_profile.test.generated_swirl",
                DamageType.TRANSFORMATIVE_REACTION,
                frozenset({"test.generated.swirl"}),
                frozenset({DamageReactionCapability.SECONDARY_AMPLIFYING}),
            ),
        )
    )


def _swirl_settlement_coordinator(assembled):
    reaction_runtime = create_default_reaction_bootstrap().create_runtime()
    handler = DamageRequestHandler(
        assembled.damage_handler.resolver,
        profile_registry=DamageProfileRegistry(assembled.damage_handler.profile_registry.profiles),
    )
    frame_coordinator = ElementalStateFrameCoordinator(
        assembled.aura_runtime,
        assembled.aura_icd_runtime,
        reaction_runtime,
    )
    interaction_coordinator = ElementalInteractionCoordinator(
        aura_runtime=assembled.aura_runtime,
        icd_runtime=assembled.aura_icd_runtime,
        reaction_runtime=reaction_runtime,
        damage_handler=handler,
        frame_coordinator=frame_coordinator,
        transformative_source_observer=(
            assembled.elemental_interaction_coordinator.transformative_source_observer
        ),
    )
    coordinator = ElementalSettlementCoordinator(
        interaction_coordinator,
        reaction_runtime=reaction_runtime,
        aura_runtime=assembled.aura_runtime,
        frame_coordinator=frame_coordinator,
        damage_handler=handler,
        generated_impact_damage_input_adapter=SwirlGeneratedImpactDamageInputAdapter(),
        aura_application_profile_registry=AuraApplicationProfileRegistry(
            (swirl_aura_application_profile(),)
        ),
    )
    return coordinator, handler


def _swirl_batch(root_work_id: str, aura_kind: AuraKind) -> ReactionGeneratedImpactBatch:
    return _swirl_resolution(root_work_id, aura_kind).generated_impact_batches[0]


def _swirl_resolution(root_work_id: str, aura_kind: AuraKind):
    source = ElementalSourceRef("character:slot_1", root_work_id)
    request = ReactionEvaluationRequest(
        interaction_id=f"interaction:{root_work_id}",
        target_impact_ref=f"impact:{root_work_id}",
        frame=0,
        order=0,
        source_ref=source,
        subject_ref=ANCHOR,
        incoming_element=Element.ANEMO,
        incoming_amount=AuraAmount(1),
        observed_aura=AuraView(
            ANCHOR,
            (
                AuraComponent(
                    AuraInstanceRef(f"aura:{root_work_id}"),
                    aura_kind,
                    (
                        AuraContribution(
                            AuraContributionRef(f"contribution:{root_work_id}"),
                            source,
                            AuraAmount("0.8"),
                            source,
                            0,
                            0,
                            0,
                        ),
                    ),
                    AuraStrength.WEAK,
                    source,
                    0,
                    0,
                    0,
                ),
            ),
        ),
        transformative_source_observation=TransformativeSourceObservation(
            source_ref=source,
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=90,
            elemental_mastery=0.0,
            level_multiplier_table_key="character",
            level_multiplier=1446.853,
            source_observation_ref=f"observation:{root_work_id}",
            source_owner_slot=1,
        ),
    )
    resolution = ReactionRuntime(ReactionRegistry((swirl_definition(),))).evaluate(request)
    assert resolution.occurrence is not None
    assert len(resolution.generated_impact_batches) == 1
    return resolution


def _profile_registry() -> AuraApplicationProfileRegistry:
    return AuraApplicationProfileRegistry(
        (
            AuraApplicationProfile(
                profile_key="aura_application_profile.test.generated",
                decay_profile_policy=AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT,
            ),
        )
    )


def _assemble(tmp_path: Path):
    asset_db = tmp_path / "assets.db"
    write_minimal_static_asset_database(asset_db)
    return SimulationAssembler(
        SQLiteAssetRepository(asset_db),
    ).assemble(
        SimulationConfig.from_mapping(
            {
                "schema_version": 1,
                "kind": "simulation_config",
                "meta": {"name": "generated reaction impacts", "description": ""},
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
                        for target_id, position in (
                            ("target_1", 0.0),
                            ("target_2", 6.0),
                            ("target_3", 6.01),
                        )
                    ]
                },
                "input_trace": [],
                "rules": {"enabled": []},
                "run_options": {"max_frames": 120},
            }
        )
    )
