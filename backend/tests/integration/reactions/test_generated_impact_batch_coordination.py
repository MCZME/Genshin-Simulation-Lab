"""生成 Impact 批次在元素结算协调器中的集成测试。"""

from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    ElementalInteractionBatchRecord,
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
from genshin_sim.core.systems.aura import (
    AuraApplicationProfile,
    AuraApplicationProfileRegistry,
    AuraApplicationRequest,
    AuraDecayProfilePolicy,
    AuraStrength,
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
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
    ReactionGeneratedImpactDamageComponent,
    ReactionGeneratedImpactProvenance,
    SwirlEmissionSelection,
    TransformativeSourceObservation,
)

ROOT_WORK_ID = "root:test-generated-impact"
SOURCE = ElementalSourceRef("character:slot_1", ROOT_WORK_ID)
ANCHOR = ElementalSubjectRef.target("target:target_1")
TARGET = ElementalSubjectRef.target("target:target_2")


def test_generated_electro_hydro_batch_freezes_targets_and_commits_common_aura_plan(
    reaction_assembled,
):
    assembled = reaction_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
    reaction_assembled,
):
    assembled = reaction_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
    reaction_assembled,
):
    assembled = reaction_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
    reaction_assembled,
):
    assembled = reaction_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
    reaction_assembled,
):
    assembled = reaction_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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
    reaction_assembled,
):
    assembled = reaction_assembled(
        meta_name="generated reaction impacts", max_frames=120, target_positions=(0.0, 6.0, 6.01)
    )
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


def _profile_registry() -> AuraApplicationProfileRegistry:
    return AuraApplicationProfileRegistry(
        (
            AuraApplicationProfile(
                profile_key="aura_application_profile.test.generated",
                decay_profile_policy=AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT,
            ),
        )
    )
