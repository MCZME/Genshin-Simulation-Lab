"""激化/绽放候选错误分支与原子性集成测试。"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from genshin_sim.core.coordination.elemental_reaction import BloomCoreTriggerError
from genshin_sim.core.elements import AuraAmount, Element, ElementalSourceRef
from genshin_sim.core.systems.reaction import UnsupportedDendroReactionCandidateError
from tests.helpers.reactions import (
    aura_request,
    bloom_core_trigger_request,
    create_bloom_core,
    establish_quicken,
    establish_quicken_with_remaining_dendro,
)


def test_anemo_on_quicken_is_rejected_before_writing(reaction_assembled) -> None:
    assembled = reaction_assembled(
        meta_name="quicken and bloom golden",
        max_frames=1000,
        target_resistances={"electro": 0.1, "dendro": 0.1},
        elemental_mastery=0.0,
    )
    target_ref = establish_quicken(assembled)
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
            aura_request(
                Element.ANEMO,
                "golden:unsupported:anemo",
                impact_key="golden.reactions.application",
            ),
        )

    assert assembled.aura_runtime.snapshot() == aura_before
    assert assembled.reaction_runtime.snapshot(0) == reaction_before
    assert assembled.aura_icd_runtime.snapshot() == icd_before
    assert len(assembled.damage_handler.records) == damage_count
    assert assembled.reaction_runtime.quicken_state_for(target_ref) is not None


def test_bloom_core_contact_requires_matching_committed_impact(reaction_assembled) -> None:
    assembled = reaction_assembled(
        meta_name="quicken and bloom golden",
        max_frames=1000,
        target_resistances={"electro": 0.1, "dendro": 0.1},
        elemental_mastery=0.0,
    )
    core = create_bloom_core(assembled, "golden:bloom-contact-evidence")
    request = bloom_core_trigger_request(
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


def test_character_damage_prevalidation_does_not_consume_gate(reaction_assembled) -> None:
    assembled = reaction_assembled(
        meta_name="quicken and bloom golden",
        max_frames=1000,
        target_resistances={"electro": 0.1, "dendro": 0.1},
        elemental_mastery=0.0,
    )
    create_bloom_core(assembled, "golden:bloom-character-prevalidation")
    damage_count = len(assembled.damage_handler.records)
    gate_records = assembled.reaction_runtime.gate_records
    assembled.elemental_settlement_coordinator.character_damage_taken_coordinator = None

    with pytest.raises(RuntimeError, match="CharacterDamageTakenCoordinator"):
        assembled.elemental_settlement_coordinator.update_frame(assembled.context, 360)

    assert len(assembled.damage_handler.records) == damage_count
    assert assembled.reaction_runtime.gate_records == gate_records


def test_hydro_rejects_unconfirmed_dendro_and_quicken_coexistence(
    reaction_assembled,
) -> None:
    assembled = reaction_assembled(
        meta_name="quicken and bloom golden",
        max_frames=1000,
        target_resistances={"electro": 0.1, "dendro": 0.1},
        elemental_mastery=0.0,
    )
    establish_quicken_with_remaining_dendro(assembled)
    aura_before = assembled.aura_runtime.snapshot()
    reaction_before = assembled.reaction_runtime.snapshot(0)

    with pytest.raises(
        UnsupportedDendroReactionCandidateError,
        match="同时进入普通草与激元素绽放候选",
    ):
        assembled.elemental_settlement_coordinator.settle_aura_impact(
            assembled.context,
            aura_request(
                Element.HYDRO,
                "golden:bloom-ambiguous-hydro",
                impact_key="golden.reactions.application",
            ),
        )

    assert assembled.aura_runtime.snapshot() == aura_before
    assert assembled.reaction_runtime.snapshot(0) == reaction_before
