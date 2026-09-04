# 单一关注点：剧变反应结算 golden。
from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    RESISTANCE_PHYSICAL,
    AttributeQuery,
    AttributeSubjectRef,
)
from genshin_sim.core.elements import (
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraStrength
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_TRANSFORMATIVE_REACTION
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
        if record.result.formula_key == FORMULA_KEY_TRANSFORMATIVE_REACTION
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
        if record.result.formula_key == FORMULA_KEY_TRANSFORMATIVE_REACTION
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
        if record.result.formula_key == FORMULA_KEY_TRANSFORMATIVE_REACTION
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
