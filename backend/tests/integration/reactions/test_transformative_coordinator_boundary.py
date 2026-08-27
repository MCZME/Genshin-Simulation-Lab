"""剧变反应协调器错误与边界行为集成测试。"""

from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import Element, ElementalSourceRef, ElementalSubjectRef
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


def test_round_one_buff_fact_blocks_reentrant_buff_write_without_inserting_events(
    reaction_assembled,
):
    assembled = reaction_assembled(meta_name="transformative reaction settlement", max_frames=1)
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


def test_effect_group_records_self_candidate_as_blocked_relation(reaction_assembled):
    assembled = reaction_assembled(meta_name="transformative reaction settlement", max_frames=1)
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


def test_multi_target_root_uses_unique_round_one_work_ids(reaction_assembled):
    assembled = reaction_assembled(
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


def test_single_round_does_not_limit_effect_groups_to_sixty_four(reaction_assembled):
    target_positions = tuple(float(index * 10) for index in range(65))
    assembled = reaction_assembled(
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
