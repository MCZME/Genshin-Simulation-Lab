# 单一关注点：扩散生产 golden 机制族。
from __future__ import annotations

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    DefaultReactionTargetEligibilityPort,
    ElementalInteractionBatchRecord,
    ElementalInteractionCoordinator,
    ElementalSettlementCoordinator,
    ElementalStateFrameCoordinator,
    ReactionTargetCapability,
    ReactionTargetEligibility,
    ReactionTargetRelation,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.impacts import (
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationProfileRegistry,
    AuraApplicationRequest,
    AuraComponent,
    AuraContribution,
    AuraContributionRef,
    AuraInstanceRef,
    AuraLossPolicy,
    AuraStrength,
    AuraView,
)
from genshin_sim.core.systems.damage import (
    DamageProfileRegistry,
    DamageRequestHandler,
    DamageType,
)
from genshin_sim.core.systems.reaction import (
    ReactionEvaluationRequest,
    ReactionGeneratedImpactBatch,
    ReactionRegistry,
    ReactionRuntime,
    TransformativeSourceObservation,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import (
    SwirlGeneratedImpactDamageInputAdapter,
    swirl_aura_application_profile,
    swirl_definition,
)

ANCHOR = ElementalSubjectRef.target("target:target_1")
TARGET = ElementalSubjectRef.target("target:target_2")


@pytest.mark.parametrize(
    ("aura_kind", "output_element", "damage_element"),
    (
        (AuraKind.PYRO, Element.PYRO, Element.PYRO),
        (AuraKind.ELECTRO, Element.ELECTRO, Element.ELECTRO),
        (AuraKind.CRYO, Element.CRYO, Element.CRYO),
    ),
)
def test_swirl_non_hydro_emission_applies_damage_and_regular_aura_to_six_meter_targets(
    golden_assembled,
    aura_kind: AuraKind,
    output_element: Element,
    damage_element: Element,
):
    assembled = golden_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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


def test_swirl_hydro_emission_applies_aura_without_range_damage(golden_assembled):
    assembled = golden_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
    golden_assembled,
):
    assembled = golden_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
    golden_assembled,
):
    assembled = golden_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
    golden_assembled,
):
    assembled = golden_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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


def test_double_swirl_damage_does_not_require_aura_capability(golden_assembled):
    assembled = golden_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
    golden_assembled,
):
    assembled = golden_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
    golden_assembled,
):
    assembled = golden_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
