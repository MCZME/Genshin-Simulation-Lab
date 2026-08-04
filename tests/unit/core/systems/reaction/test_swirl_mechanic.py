from __future__ import annotations

import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.systems.aura import (
    AuraComponent,
    AuraContribution,
    AuraContributionRef,
    AuraDecayMode,
    AuraInstanceRef,
    AuraStrength,
    AuraView,
)
from genshin_sim.core.systems.damage import (
    DamageElement,
    DamageReactionCapability,
    DamageType,
)
from genshin_sim.core.systems.reaction import (
    GeneratedDamageImpactEffect,
    ReactionEvaluationRequest,
    ReactionRegistry,
    ReactionRuntime,
    SwirlEmissionSelection,
    TransformativeSourceObservation,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.gates import (
    ReactionDamageGateDecision,
    ReactionDamageGateRequest,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import (
    SWIRL_REACTION_KEY,
    SwirlGeneratedImpactDamageInputAdapter,
    SwirlSelectionError,
    swirl_aura_application_profile,
    swirl_damage_profile,
    swirl_definition,
    swirl_gate_definitions,
)

SOURCE = ElementalSourceRef("character:slot_1", "root:swirl")
TARGET = ElementalSubjectRef.target("target:target_1")


@pytest.mark.parametrize(
    ("aura_kind", "output_element", "damage_element", "has_range_damage"),
    (
        (AuraKind.PYRO, Element.PYRO, DamageElement.PYRO, True),
        (AuraKind.HYDRO, Element.HYDRO, DamageElement.HYDRO, False),
        (AuraKind.ELECTRO, Element.ELECTRO, DamageElement.ELECTRO, True),
        (AuraKind.CRYO, Element.CRYO, DamageElement.CRYO, True),
        (AuraKind.FROZEN, Element.CRYO, DamageElement.CRYO, True),
    ),
)
def test_swirl_maps_the_single_aura_to_center_damage_and_range_emission(
    aura_kind: AuraKind,
    output_element: Element,
    damage_element: DamageElement,
    has_range_damage: bool,
):
    resolution = _runtime().evaluate(_request(aura_kind, AuraAmount("0.8"), AuraAmount(1)))

    assert resolution.occurrence is not None
    occurrence = resolution.occurrence
    assert occurrence.reaction_key == SWIRL_REACTION_KEY
    assert occurrence.transition.incoming_consumed == AuraAmount(1)
    assert occurrence.transition.incoming_remaining == AuraAmount.zero()
    assert occurrence.transition.aura_consumed == AuraAmount("0.5")
    assert occurrence.transition.aura_remaining == AuraAmount("0.3")
    center_effect = occurrence.effect_groups[0].effects[0]
    assert isinstance(center_effect, GeneratedDamageImpactEffect)
    assert center_effect.damage_element is damage_element
    assert center_effect.elemental_amount == AuraAmount.zero()
    assert center_effect.can_crit is False
    assert center_effect.captured_scaling_basis.reaction_bonus == 0.0
    assert center_effect.transformative_base_multiplier == 0.6
    batch = resolution.generated_impact_batches[0]
    assert batch.parent_root_work_ref == "root:swirl"
    assert isinstance(batch.target_selection, SwirlEmissionSelection)
    assert batch.target_selection.anchor_subject_ref == TARGET
    assert batch.target_selection.radius == 6.0
    emission = batch.impacts[0]
    assert emission.element is output_element
    assert emission.elemental_amount == AuraAmount("2.2")
    assert (emission.damage_component is not None) is has_range_damage


@pytest.mark.parametrize(
    ("incoming_amount", "aura_amount", "expected_emitted", "expected_remaining_aura"),
    (
        (AuraAmount(1), AuraAmount("0.8"), AuraAmount("2.2"), AuraAmount("0.3")),
        (AuraAmount(2), AuraAmount("0.8"), AuraAmount("1.95"), AuraAmount.zero()),
        (AuraAmount(2), AuraAmount(1), AuraAmount("2.2"), AuraAmount.zero()),
        (AuraAmount(2), AuraAmount("1.6"), AuraAmount("3.45"), AuraAmount("0.6")),
    ),
)
def test_swirl_uses_the_strict_surplus_deficit_emission_formula(
    incoming_amount: AuraAmount,
    aura_amount: AuraAmount,
    expected_emitted: AuraAmount,
    expected_remaining_aura: AuraAmount,
):
    resolution = _runtime().evaluate(_request(AuraKind.PYRO, aura_amount, incoming_amount))

    assert resolution.occurrence is not None
    assert resolution.occurrence.transition.aura_remaining == expected_remaining_aura
    assert resolution.generated_impact_batches[0].impacts[0].elemental_amount == expected_emitted


def test_swirl_does_not_match_without_a_swirleable_aura():
    resolution = _runtime().evaluate(_request(None, AuraAmount.zero(), AuraAmount(1)))

    assert resolution.occurrence is None
    assert resolution.generated_impact_batches == ()


def test_swirl_rejects_unconfirmed_multiple_swirleable_auras_without_choosing_by_order():
    request = _request(AuraKind.HYDRO, AuraAmount("0.8"), AuraAmount(1))
    request = ReactionEvaluationRequest(
        request.interaction_id,
        request.target_impact_ref,
        request.frame,
        request.order,
        request.source_ref,
        request.subject_ref,
        request.incoming_element,
        request.incoming_amount,
        AuraView(
            TARGET,
            (
                _component(AuraKind.HYDRO, AuraAmount("0.8")),
                _component(AuraKind.PYRO, AuraAmount("0.8")),
            ),
        ),
        transformative_source_observation=request.transformative_source_observation,
    )

    with pytest.raises(SwirlSelectionError, match="hydro"):
        _runtime().evaluate(request)


def test_swirl_resolves_electro_hydro_in_the_confirmed_order_with_shared_emission():
    request = _request(AuraKind.HYDRO, AuraAmount("0.4"), AuraAmount(1))
    request = ReactionEvaluationRequest(
        request.interaction_id,
        request.target_impact_ref,
        request.frame,
        request.order,
        request.source_ref,
        request.subject_ref,
        request.incoming_element,
        request.incoming_amount,
        AuraView(
            TARGET,
            (
                _component(AuraKind.HYDRO, AuraAmount("0.4")),
                _component(AuraKind.ELECTRO, AuraAmount("0.4")),
            ),
        ),
        transformative_source_observation=request.transformative_source_observation,
    )

    resolution = _runtime().evaluate(request)

    assert [
        occurrence.direction_key
        for step in resolution.sequence.steps
        for occurrence in step.occurrences
    ] == ["incoming_anemo_on_electro", "incoming_anemo_on_hydro"]
    batch = resolution.generated_impact_batches[0]
    assert len(batch.parent_occurrence_refs) == 2
    assert [impact.element for impact in batch.impacts] == [Element.ELECTRO, Element.HYDRO]
    assert {impact.elemental_amount for impact in batch.impacts} == {AuraAmount("1.2")}


def test_swirl_hidden_cryo_then_frozen_consumption_creates_one_cryo_occurrence():
    request = _request(AuraKind.CRYO, AuraAmount("0.4"), AuraAmount(1))
    request = ReactionEvaluationRequest(
        request.interaction_id,
        request.target_impact_ref,
        request.frame,
        request.order,
        request.source_ref,
        request.subject_ref,
        request.incoming_element,
        request.incoming_amount,
        AuraView(
            TARGET,
            (
                _component(AuraKind.CRYO, AuraAmount("0.4")),
                _component(AuraKind.FROZEN, AuraAmount("0.4")),
            ),
        ),
        transformative_source_observation=request.transformative_source_observation,
    )

    resolution = _runtime().evaluate(request)

    assert resolution.occurrence is not None
    assert resolution.occurrence.direction_key == "incoming_anemo_on_cryo"
    assert [
        occurrence.direction_key
        for step in resolution.sequence.steps
        for occurrence in step.occurrences
    ] == ["incoming_anemo_on_cryo"]
    assert resolution.sequence.steps[1].selected_candidate_keys == ("incoming_anemo_on_frozen",)
    assert len(resolution.sequence.steps[1].elemental_transition_effects) == 1
    batch = resolution.generated_impact_batches[0]
    assert [impact.element for impact in batch.impacts] == [Element.CRYO]
    assert batch.impacts[0].elemental_amount == AuraAmount("1.2")


def test_default_bootstrap_registers_swirl():
    definitions = create_default_reaction_bootstrap().reaction_registry.definitions

    assert SWIRL_REACTION_KEY in {definition.reaction_key for definition in definitions}


def test_swirl_test_assembly_declares_regular_aura_profile_damage_profile_and_gates():
    aura_profile = swirl_aura_application_profile()
    damage_profile = swirl_damage_profile()
    gates = swirl_gate_definitions()

    assert aura_profile.profile_key == "aura_application_profile.reaction.swirl"
    assert damage_profile.damage_type is DamageType.TRANSFORMATIVE_REACTION
    assert damage_profile.main_attack_tags == frozenset({SWIRL_REACTION_KEY})
    assert damage_profile.reaction_capabilities == frozenset(
        {DamageReactionCapability.SECONDARY_AMPLIFYING}
    )
    assert [gate.damage_kind_key for gate in gates] == [
        "reaction_damage.swirl.pyro",
        "reaction_damage.swirl.hydro",
        "reaction_damage.swirl.electro",
        "reaction_damage.swirl.cryo",
    ]
    assert {(gate.window_frames, gate.max_damage_instances) for gate in gates} == {(30, 2)}


def test_swirl_range_damage_adapter_uses_the_captured_source_and_fixed_multiplier():
    resolution = _runtime().evaluate(_request(AuraKind.PYRO, AuraAmount("0.8"), AuraAmount(1)))
    assert resolution.occurrence is not None
    batch = resolution.generated_impact_batches[0]
    impact = batch.impacts[0]

    result = SwirlGeneratedImpactDamageInputAdapter().transformative_input(
        batch=batch,
        impact=impact,
    )

    assert result.occurrence_ref == resolution.occurrence.occurrence_ref
    assert result.level_multiplier == 1.0
    assert result.elemental_mastery == 100.0
    assert result.mastery_bonus == pytest.approx(16 * 100 / 2100)
    assert result.reaction_bonus == 0.0
    assert result.base_multiplier == 0.6


def test_swirl_range_damage_adapter_rejects_hydro_emission_without_damage_component():
    resolution = _runtime().evaluate(_request(AuraKind.HYDRO, AuraAmount("0.8"), AuraAmount(1)))
    batch = resolution.generated_impact_batches[0]

    with pytest.raises(ValueError, match="没有 Damage 组件"):
        SwirlGeneratedImpactDamageInputAdapter().transformative_input(
            batch=batch,
            impact=batch.impacts[0],
        )


def test_swirl_gate_is_independent_for_each_output_element():
    runtime = ReactionRuntime(
        ReactionRegistry(),
        gate_definitions=swirl_gate_definitions(),
    )
    pyro_key, hydro_key, electro_key, cryo_key = (
        gate.gate_definition_key for gate in swirl_gate_definitions()
    )

    assert [_prepare_gate(runtime, pyro_key, index).decision for index in range(3)] == [
        ReactionDamageGateDecision.ALLOWED,
        ReactionDamageGateDecision.ALLOWED,
        ReactionDamageGateDecision.BLOCKED,
    ]
    assert _prepare_gate(runtime, electro_key, 0).decision is ReactionDamageGateDecision.ALLOWED
    assert {record.slot_key.gate_definition_key for record in runtime.gate_records} == {
        pyro_key,
        electro_key,
    }
    assert {gate.gate_definition_key for gate in swirl_gate_definitions()} == {
        pyro_key,
        hydro_key,
        electro_key,
        cryo_key,
    }


def _runtime() -> ReactionRuntime:
    return ReactionRuntime(ReactionRegistry((swirl_definition(),)))


def _request(
    aura_kind: AuraKind | None,
    aura_amount: AuraAmount,
    incoming_amount: AuraAmount,
) -> ReactionEvaluationRequest:
    components = () if aura_kind is None else (_component(aura_kind, aura_amount),)
    return ReactionEvaluationRequest(
        "interaction:swirl",
        "impact:target",
        0,
        0,
        SOURCE,
        TARGET,
        Element.ANEMO,
        incoming_amount,
        AuraView(TARGET, components),
        transformative_source_observation=TransformativeSourceObservation(
            SOURCE,
            TransformativeReactionSourceKind.CHARACTER,
            90,
            100.0,
            "character.level_multiplier.v1",
            1.0,
            "observation:swirl-source",
            1,
        ),
    )


def _component(aura_kind: AuraKind, amount: AuraAmount) -> AuraComponent:
    state_link_ref = (
        ElementalStateLinkRef("elemental-state-link:swirl")
        if aura_kind is AuraKind.FROZEN
        else None
    )
    return AuraComponent(
        AuraInstanceRef(f"aura:{aura_kind.value}"),
        aura_kind,
        (
            AuraContribution(
                AuraContributionRef(f"contribution:{aura_kind.value}"),
                SOURCE,
                amount,
                SOURCE,
                0,
                0,
                0,
            ),
        ),
        AuraStrength.WEAK,
        SOURCE,
        0,
        0,
        0,
        state_link_refs=() if state_link_ref is None else (state_link_ref,),
        decay_mode=(
            AuraDecayMode.STATE_LINKED if state_link_ref is not None else AuraDecayMode.STANDARD
        ),
    )


def _prepare_gate(
    runtime: ReactionRuntime,
    definition_key: str,
    index: int,
):
    operation_id = f"gate:swirl:{definition_key}:{index}:{runtime.version}"
    planner = runtime.begin_gate_batch(0, operation_id)
    resolution = planner.prepare(
        ReactionDamageGateRequest(
            gate_request_ref=f"{operation_id}:request",
            frame=0,
            definition=runtime.gate_definition(definition_key),
            trigger_source_ref=ElementalSourceRef("character:slot_1"),
            damage_target_ref=TARGET,
            parent_occurrence_ref=f"{operation_id}:occurrence",
            parent_effect_ref=f"{operation_id}:effect",
        )
    )
    plan = planner.seal()
    runtime.validate_gate_plan(plan)
    runtime.commit_prevalidated_gate_plan(plan)
    return resolution
