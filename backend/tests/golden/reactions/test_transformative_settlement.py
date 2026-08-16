# 超 500 行说明：单一关注点（剧变反应结算 golden），暂不拆分。
from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    RESISTANCE_PHYSICAL,
    AttributeQuery,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import (
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraStrength
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffModifierValue,
    BuffReentrancyError,
)
from genshin_sim.core.systems.damage import DamageType, DamageValidationError
from genshin_sim.core.systems.reaction import ReactionStoreConflictError
from tests.helpers.reactions import aura_request


@pytest.mark.parametrize(
    ("aura_element", "incoming_element", "reaction_key", "expected_damage"),
    (
        (Element.ELECTRO, Element.PYRO, "reaction.overloaded", 3978.84575),
        (Element.PYRO, Element.ELECTRO, "reaction.overloaded", 3978.84575),
        (Element.ELECTRO, Element.CRYO, "reaction.superconduct", 2170.2795),
        (Element.CRYO, Element.ELECTRO, "reaction.superconduct", 2170.2795),
    ),
)
def test_transformative_reactions_use_confirmed_damage_and_exact_consumption(
    golden_assembled,
    aura_element: Element,
    incoming_element: Element,
    reaction_key: str,
    expected_damage: float,
):
    assembled = golden_assembled(meta_name="transformative reaction settlement", max_frames=1)
    target_ref = ElementalSubjectRef.target("target:target_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "initial:aura",
            "initial:application",
            "initial:impact",
            0,
            0,
            ElementalSourceRef("initial"),
            target_ref,
            aura_element,
            AuraStrength.WEAK,
        )
    )

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            incoming_element,
            request_id="transformative:input",
            impact_key="golden.transformative.application",
        ),
    )

    reaction_records = tuple(
        record
        for record in assembled.damage_handler.records
        if record.result.damage_type is DamageType.TRANSFORMATIVE_REACTION
    )
    assert len(reaction_records) == 1
    result = reaction_records[0].result
    assert result.final_damage == pytest.approx(expected_damage)
    assert result.crit_outcome.value == "not_applicable"
    assert result.trace_metadata["defense_policy"] == "approximate_unity"
    assert not assembled.aura_runtime.view(target_ref).components
    effect_record = assembled.elemental_settlement_coordinator.records[-1]
    assert effect_record.settlement_round == 1
    assert effect_record.work_ids == ("transformative:input:round:1:effect_group:0:0",)
    assert effect_record.parent_work_id == "transformative:input"
    assert result.reaction_details is not None
    assert result.reaction_details.reaction_profile_key is not None
    assert reaction_key.removeprefix("reaction.") in result.reaction_details.reaction_profile_key


def test_overloaded_gate_blocks_second_damage_but_not_occurrence(golden_assembled):
    assembled = golden_assembled(meta_name="transformative reaction settlement", max_frames=1)
    target_ref = ElementalSubjectRef.target("target:target_1")
    for index in range(2):
        assembled.aura_runtime.apply(
            AuraApplicationRequest(
                f"aura:{index}",
                f"application:{index}",
                f"impact:{index}",
                0,
                index,
                ElementalSourceRef("initial"),
                target_ref,
                Element.ELECTRO,
                AuraStrength.WEAK,
            )
        )
        assembled.elemental_settlement_coordinator.settle_aura_impact(
            assembled.context,
            aura_request(
                Element.PYRO,
                request_id=f"overloaded:input:{index}",
                impact_key="golden.transformative.application",
            ),
        )

    reaction_records = tuple(
        record
        for record in assembled.damage_handler.records
        if record.result.damage_type is DamageType.TRANSFORMATIVE_REACTION
    )
    assert len(reaction_records) == 1
    assert len(assembled.reaction_runtime.gate_records) == 1
    assert assembled.reaction_runtime.gate_records[0].accepted_count == 1
    outcomes = assembled.elemental_settlement_coordinator.records[-1].target_effect_outcomes
    assert (
        next(
            outcome.damage_outcome
            for outcome in outcomes
            if outcome.subject_ref == ElementalSubjectRef.target("target:target_1")
        )
        == "blocked_by_gate"
    )


def test_superconduct_applies_and_replaces_physical_resistance_reduction(golden_assembled):
    assembled = golden_assembled(meta_name="transformative reaction settlement", max_frames=1)
    target_ref = ElementalSubjectRef.target("target:target_1")
    for index in range(2):
        assembled.aura_runtime.apply(
            AuraApplicationRequest(
                f"aura:{index}",
                f"application:{index}",
                f"impact:{index}",
                0,
                index,
                ElementalSourceRef("initial"),
                target_ref,
                Element.ELECTRO,
                AuraStrength.WEAK,
            )
        )
        assembled.elemental_settlement_coordinator.settle_aura_impact(
            assembled.context,
            aura_request(
                Element.CRYO,
                request_id=f"superconduct:input:{index}",
                impact_key="golden.transformative.application",
            ),
        )

    active = assembled.buff_store.active(
        0,
        target_ref=AttributeSubjectRef.target("target:target_1"),
    )
    assert len(active) == 1
    assert active[0].expires_at_frame == 720
    resistance = assembled.attribute_runtime.resolver.resolve(
        AttributeQuery(
            subject_ref=AttributeSubjectRef.target("target:target_1"),
            attribute_key=RESISTANCE_PHYSICAL,
            frame=0,
        )
    )
    assert resistance.final_value == pytest.approx(-0.40)
    assert len(assembled.reaction_runtime.gate_records) == 1
    assert assembled.reaction_runtime.gate_records[0].accepted_count == 2


def test_reaction_effect_group_includes_five_meter_boundary_with_stable_targets(golden_assembled):
    assembled = golden_assembled(
        meta_name="transformative reaction settlement",
        max_frames=1,
        target_positions=(0.0, 5.0, 5.01),
    )
    target_ref = ElementalSubjectRef.target("target:target_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "initial:aura",
            "initial:application",
            "initial:impact",
            0,
            0,
            ElementalSourceRef("initial"),
            target_ref,
            Element.ELECTRO,
            AuraStrength.WEAK,
        )
    )

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            request_id="overloaded:range",
            impact_key="golden.transformative.application",
        ),
    )

    targets = tuple(
        record.result.target_ref.entity_id
        for record in assembled.damage_handler.records
        if record.result.damage_type is DamageType.TRANSFORMATIVE_REACTION
    )
    assert targets == ("target:target_1", "target:target_2")


def test_overloaded_blunt_shatters_when_overloaded_damage_gate_blocks(golden_assembled):
    assembled = golden_assembled(
        meta_name="transformative reaction settlement",
        max_frames=1,
        target_positions=(0.0, 1.0),
    )
    overloaded_target = ElementalSubjectRef.target("target:target_1")
    frozen_target = ElementalSubjectRef.target("target:target_2")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "overloaded:prime:electro",
            "overloaded:prime:electro:application",
            "overloaded:prime:electro:impact",
            0,
            0,
            ElementalSourceRef("initial"),
            overloaded_target,
            Element.ELECTRO,
            AuraStrength.WEAK,
        )
    )
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            request_id="overloaded:blunt:prime-gate",
            impact_key="golden.transformative.application",
        ),
    )
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "frozen:cryo",
            "frozen:cryo:application",
            "frozen:cryo:impact",
            0,
            0,
            ElementalSourceRef("initial"),
            frozen_target,
            Element.CRYO,
            AuraStrength.WEAK,
        )
    )
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.HYDRO,
            request_id="overloaded:blunt:freeze",
            target_refs=("target_2",),
            impact_key="golden.transformative.application",
        ),
    )
    assert assembled.reaction_runtime.frozen_state_for(frozen_target) is not None

    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "overloaded:electro",
            "overloaded:electro:application",
            "overloaded:electro:impact",
            0,
            1,
            ElementalSourceRef("initial"),
            overloaded_target,
            Element.ELECTRO,
            AuraStrength.WEAK,
        )
    )
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            request_id="overloaded:blunt:trigger",
            impact_key="golden.transformative.application",
        ),
    )

    assert assembled.reaction_runtime.frozen_state_for(frozen_target) is None
    assert assembled.aura_runtime.view(frozen_target).component_for(AuraKind.FROZEN) is None
    overloaded_effect_record = assembled.elemental_settlement_coordinator.records[-2]
    assert overloaded_effect_record.settlement_round == 1
    assert len(overloaded_effect_record.reaction_occurrence_refs) == 1
    assert len(overloaded_effect_record.reaction_effect_groups) == 1
    frozen_target_outcome = next(
        outcome
        for outcome in overloaded_effect_record.target_effect_outcomes
        if outcome.subject_ref == frozen_target
    )
    assert frozen_target_outcome.damage_outcome == "blocked_by_gate"
    shattered_record = assembled.elemental_settlement_coordinator.records[-1]
    assert shattered_record.settlement_round == 2
    assert shattered_record.parent_work_id == overloaded_effect_record.work_ids[0]
    shattered_damage = tuple(
        record
        for record in assembled.damage_handler.records
        if record.result.reaction_details is not None
        and record.result.reaction_details.reaction_profile_key == "reaction_profile.shattered"
    )
    assert len(shattered_damage) == 1
    assert shattered_damage[0].result.target_ref.entity_id == frozen_target.entity_id
    assert shattered_damage[0].result.element.value == "physical"


def test_round_one_buff_fact_blocks_reentrant_buff_write_without_inserting_events(golden_assembled):
    assembled = golden_assembled(meta_name="transformative reaction settlement", max_frames=1)
    target_ref = ElementalSubjectRef.target("target:target_1")
    reentrancy_errors: list[Exception] = []

    def reenter_buff_runtime(_: object) -> None:
        request = ApplyBuffRequest(
            request_id="test:reentrant:buff",
            frame=0,
            order=99,
            definition_key="buff.reaction.superconduct.physical_resistance_reduction",
            target_ref=AttributeSubjectRef.target("target:target_1"),
            source_context=RuntimeSourceRef(RuntimeSourceKind.MECHANIC, "test.reentrant"),
            duration_frames=720,
            modifier_values=(BuffModifierValue("resistance.physical.reduction", -0.40),),
        )
        with pytest.raises(BuffReentrancyError) as exc_info:
            assembled.buff_runtime.apply(request)
        reentrancy_errors.append(exc_info.value)
        with pytest.raises(DamageValidationError) as exc_info:
            assembled.damage_handler.commit_prepared_records(())
        reentrancy_errors.append(exc_info.value)
        gate_plan = assembled.reaction_runtime.begin_gate_batch(
            0,
            "test:reentrant:gate",
        ).seal()
        with pytest.raises(ReactionStoreConflictError) as exc_info:
            assembled.reaction_runtime.commit_prevalidated_gate_plan(gate_plan)
        reentrancy_errors.append(exc_info.value)

    assembled.context.events.subscribe(EventType.BUFF_APPLIED, reenter_buff_runtime)
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "initial:aura",
            "initial:application",
            "initial:impact",
            0,
            0,
            ElementalSourceRef("initial"),
            target_ref,
            Element.ELECTRO,
            AuraStrength.WEAK,
        )
    )

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.CRYO,
            request_id="superconduct:reentrant",
            impact_key="golden.transformative.application",
        ),
    )

    assert len(reentrancy_errors) == 3
    assert [event.event_type for event in assembled.context.events.frame_events] == [
        EventType.AURA_ICD_RESOLVED,
        EventType.AURA_INTERACTION_RESOLVED,
        EventType.REACTION_OCCURRED,
        EventType.ELEMENTAL_INTERACTION_RESOLVED,
        EventType.BUFF_APPLIED,
        EventType.DAMAGE_RESOLVED,
        EventType.ELEMENTAL_INTERACTION_RESOLVED,
    ]


def test_effect_group_records_self_candidate_as_blocked_relation(golden_assembled):
    assembled = golden_assembled(meta_name="transformative reaction settlement", max_frames=1)
    target_ref = ElementalSubjectRef.target("target:target_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "initial:aura",
            "initial:application",
            "initial:impact",
            0,
            0,
            ElementalSourceRef("initial"),
            target_ref,
            Element.ELECTRO,
            AuraStrength.WEAK,
        )
    )

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            request_id="overloaded:self-audit",
            impact_key="golden.transformative.application",
        ),
    )

    self_outcome = next(
        outcome
        for outcome in assembled.elemental_settlement_coordinator.records[-1].target_effect_outcomes
        if outcome.subject_ref == ElementalSubjectRef.character("player:active")
    )
    assert self_outcome.damage_outcome == "blocked_relation"


def test_multi_target_root_uses_unique_round_one_work_ids(golden_assembled):
    assembled = golden_assembled(
        meta_name="transformative reaction settlement",
        max_frames=1,
        target_positions=(0.0, 10.0),
    )
    for target_id in ("target_1", "target_2"):
        assembled.aura_runtime.apply(
            AuraApplicationRequest(
                f"initial:{target_id}",
                f"initial:{target_id}:application",
                f"initial:{target_id}:impact",
                0,
                0,
                ElementalSourceRef("initial"),
                ElementalSubjectRef.target(f"target:{target_id}"),
                Element.ELECTRO,
                AuraStrength.WEAK,
            )
        )

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            request_id="overloaded:multi-target-root",
            target_refs=("target_1", "target_2"),
            impact_key="golden.transformative.application",
        ),
    )

    follow_up_records = assembled.elemental_settlement_coordinator.records[1:]
    assert len(follow_up_records) == 2
    assert len({record.work_ids[0] for record in follow_up_records}) == 2
    assert (
        len(
            tuple(
                record
                for record in assembled.damage_handler.records
                if record.result.damage_type is DamageType.TRANSFORMATIVE_REACTION
            )
        )
        == 2
    )


def test_single_round_does_not_limit_effect_groups_to_sixty_four(golden_assembled):
    target_positions = tuple(float(index * 10) for index in range(65))
    assembled = golden_assembled(
        meta_name="transformative reaction settlement",
        max_frames=1,
        target_positions=target_positions,
    )
    target_refs = tuple(f"target_{index}" for index in range(1, len(target_positions) + 1))
    for target_id in target_refs:
        assembled.aura_runtime.apply(
            AuraApplicationRequest(
                f"initial:{target_id}",
                f"initial:{target_id}:application",
                f"initial:{target_id}:impact",
                0,
                0,
                ElementalSourceRef("initial"),
                ElementalSubjectRef.target(f"target:{target_id}"),
                Element.ELECTRO,
                AuraStrength.WEAK,
            )
        )

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            request_id="overloaded:many-groups",
            target_refs=target_refs,
            impact_key="golden.transformative.application",
        ),
    )

    assert len(assembled.elemental_settlement_coordinator.records) == 66
    assert all(
        record.settlement_round == 1
        for record in assembled.elemental_settlement_coordinator.records[1:]
    )
