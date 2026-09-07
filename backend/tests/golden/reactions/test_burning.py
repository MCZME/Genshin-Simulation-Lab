from __future__ import annotations

from fractions import Fraction

import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
)
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_TRANSFORMATIVE_REACTION
from genshin_sim.core.systems.reaction.mechanics.burning import BURNING_DAMAGE_KIND_KEY
from genshin_sim.core.systems.reaction.states import ScheduledStateTickCause
from tests.helpers.reactions import advance_to, apply_aura, aura_request, target_subject

BURNING_DAMAGE = 361.71325
ESTABLISH_SOURCE = ElementalSourceRef("character:slot_1", "golden:burning:establish")
MAINTENANCE_SOURCE = ElementalSourceRef("character:slot_1", "golden:burning:maintenance")


@pytest.mark.parametrize(
    ("first", "incoming"),
    (
        (Element.DENDRO, Element.PYRO),
        (Element.PYRO, Element.DENDRO),
    ),
)
def test_production_assembly_establishes_burning_and_first_damage(
    golden_assembled,
    first: Element,
    incoming: Element,
) -> None:
    assembled = golden_assembled(meta_name="burning golden")
    target_ref = target_subject()
    apply_aura(assembled, first, "golden:initial")

    record = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            incoming,
            "golden:burning:establish",
            strength=AuraStrength.STRONG,
            impact_key="golden.burning.application",
        ),
    )

    state = assembled.reaction_runtime.burning_state_for(target_ref)
    aura = assembled.aura_runtime.view(target_ref)
    dendro = aura.component_for(AuraKind.DENDRO)
    burning = aura.component_for(AuraKind.BURNING)
    results = _burning_results(assembled)

    assert state is not None
    assert len(record.reaction_occurrence_refs) == 1
    assert record.reaction_occurrence_refs[0] == state.created_by_occurrence_ref
    assert burning is not None
    assert burning.current_amount == AuraAmount(2)
    assert dendro is not None
    assert dendro.current_amount == AuraAmount(Fraction(8, 5))
    assert dendro.decay_mode.value == "reaction_managed"
    assert state.next_damage_tick_frame == 15
    assert state.next_damage_tick_index == 1
    assert state.next_pyro_application_frame == 15
    assert state.next_pyro_application_index == 1
    assert state.current_effect_owner == ESTABLISH_SOURCE
    assert len(results) == 1
    assert results[0].final_damage == pytest.approx(BURNING_DAMAGE)
    assert results[0].crit_outcome.value == "not_applicable"
    assert assembled.reaction_runtime.gate_records[0].accepted_count == 1
    assert assembled.reaction_runtime.gate_records[0].cause is not None


def test_timeline_covers_ticks_source_replacement_gate_and_extinguish(
    golden_assembled,
) -> None:
    assembled = golden_assembled(meta_name="burning golden", max_frames=240)
    target_ref = target_subject()
    apply_aura(assembled, Element.DENDRO, "golden:initial")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            "golden:burning:establish",
            strength=AuraStrength.STRONG,
            impact_key="golden.burning.application",
        ),
    )
    established = assembled.reaction_runtime.burning_state_for(target_ref)
    assert established is not None
    occurrence_count_after_establish = len(
        [
            record
            for record in assembled.elemental_settlement_coordinator.records
            if record.reaction_occurrence_refs
        ]
    )

    advance_to(assembled, 15)

    after_first_cycle = assembled.reaction_runtime.burning_state_for(target_ref)
    assert after_first_cycle is not None
    assert after_first_cycle.instance_ref == established.instance_ref
    assert after_first_cycle.next_damage_tick_frame == 30
    assert after_first_cycle.next_damage_tick_index == 2
    assert after_first_cycle.next_pyro_application_frame == 135
    assert after_first_cycle.next_pyro_application_index == 2
    assert len(_burning_results(assembled)) == 2
    pyro = assembled.aura_runtime.view(target_ref).component_for(AuraKind.PYRO)
    assert pyro is not None
    assert pyro.current_amount > AuraAmount.zero()
    roots = _scheduled_roots(assembled)
    assert len(roots) == 1
    assert roots[0].scheduled_root_outcome == "prepared"
    assert len(roots[0].scheduled_state_tick_causes) == 2
    cause_kinds = {cause.tick_kind.value for cause in roots[0].scheduled_state_tick_causes}
    assert cause_kinds == {"burning_damage", "burning_pyro_application"}
    assert all(
        isinstance(cause, ScheduledStateTickCause) for cause in roots[0].scheduled_state_tick_causes
    )

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            "golden:burning:maintenance",
            frame=16,
            strength=AuraStrength.STRONG,
            impact_key="golden.burning.application",
        ),
    )
    maintained = assembled.reaction_runtime.burning_state_for(target_ref)
    assert maintained is not None
    assert maintained.instance_ref == established.instance_ref
    assert maintained.revision == after_first_cycle.revision + 1
    assert maintained.current_effect_owner == MAINTENANCE_SOURCE
    assert maintained.next_damage_tick_frame == 30
    assert maintained.next_damage_tick_index == 2
    assert maintained.next_pyro_application_frame == 135
    assert maintained.next_pyro_application_index == 2
    assert len(_burning_results(assembled)) == 2
    assert (
        len(
            [
                record
                for record in assembled.elemental_settlement_coordinator.records
                if record.reaction_occurrence_refs
            ]
        )
        == occurrence_count_after_establish
    )

    for frame in (30, 45, 60, 75, 90, 105):
        advance_to(assembled, frame)

    assert assembled.reaction_runtime.burning_state_for(target_ref) is not None
    first_window = assembled.reaction_runtime.gate_records[0]
    assert first_window.slot_key.damage_kind_key == BURNING_DAMAGE_KIND_KEY
    assert first_window.slot_key.trigger_source_ref.source_key == "character:slot_1"
    assert first_window.window_started_frame == 0
    assert first_window.ready_frame == 120
    assert first_window.accepted_count == 8
    assert len(_burning_results(assembled)) == 8

    advance_to(assembled, 120)
    assert assembled.reaction_runtime.burning_state_for(target_ref) is not None
    assert len(_burning_results(assembled)) == 9
    refreshed_window = assembled.reaction_runtime.gate_records[0]
    assert refreshed_window.window_started_frame == 120
    assert refreshed_window.ready_frame == 240
    assert refreshed_window.accepted_count == 1
    assert isinstance(refreshed_window.cause, ScheduledStateTickCause)

    while assembled.reaction_runtime.burning_state_for(target_ref) is not None:
        next_frame = assembled.reaction_runtime.next_required_frame()
        assert next_frame is not None
        advance_to(assembled, next_frame)

    assert assembled.reaction_runtime.burning_state_for(target_ref) is None
    assert assembled.aura_runtime.view(target_ref).component_for(AuraKind.BURNING) is None
    assert assembled.aura_runtime.view(target_ref).component_for(AuraKind.DENDRO) is None
    assert len(_burning_results(assembled)) >= 9
    assert all(
        result.final_damage == pytest.approx(BURNING_DAMAGE)
        for result in _burning_results(assembled)
    )


def test_parallel_cryo_and_reestablishment_on_production_path(
    golden_assembled,
) -> None:
    assembled = golden_assembled(meta_name="burning golden")
    target_ref = target_subject()
    apply_aura(assembled, Element.DENDRO, "golden:initial", strength=AuraStrength.WEAK)
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            "golden:burning:establish",
            strength=AuraStrength.WEAK,
            impact_key="golden.burning.application",
        ),
    )
    adjust = assembled.aura_runtime.begin_batch(0, "golden:burning:parallel-adjust")
    adjust.consume(
        interaction_id="golden:burning:parallel-adjust:burning",
        subject_ref=target_ref,
        aura_kind=AuraKind.BURNING,
        amount=AuraAmount(Fraction(3, 2)),
    )
    adjust.consume(
        interaction_id="golden:burning:parallel-adjust:pyro",
        subject_ref=target_ref,
        aura_kind=AuraKind.PYRO,
        amount=AuraAmount(Fraction(1, 10)),
    )
    assembled.aura_runtime.commit_prevalidated(adjust.seal())
    cryo_record = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.CRYO,
            "golden:burning:cryo-parallel",
            strength=AuraStrength.WEAK,
            impact_key="golden.burning.application",
        ),
    )

    assert len(cryo_record.reaction_occurrence_refs) == 1
    aura = assembled.aura_runtime.view(target_ref)
    assert aura.component_for(AuraKind.BURNING) is None
    assert aura.component_for(AuraKind.PYRO).current_amount == AuraAmount(Fraction(1, 5))  # type: ignore[union-attr]
    assert aura.component_for(AuraKind.DENDRO).current_amount == AuraAmount(Fraction(4, 5))  # type: ignore[union-attr]
    assert assembled.reaction_runtime.burning_state_for(target_ref) is None

    reestablish = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            "golden:burning:reestablish",
            strength=AuraStrength.WEAK,
            impact_key="golden.burning.application",
        ),
    )
    state = assembled.reaction_runtime.burning_state_for(target_ref)
    aura = assembled.aura_runtime.view(target_ref)
    burning = aura.component_for(AuraKind.BURNING)
    dendro = aura.component_for(AuraKind.DENDRO)
    assert state is not None
    assert len(reestablish.reaction_occurrence_refs) == 1
    assert reestablish.reaction_occurrence_refs[0] == state.created_by_occurrence_ref
    assert burning is not None
    assert burning.current_amount == AuraAmount(2)
    assert dendro is not None
    assert dendro.decay_mode.value == "reaction_managed"
    assert dendro.state_link_refs == (state.burning_aura_link_ref,)
    assert aura.component_for(AuraKind.PYRO) is not None


def test_burning_extinguish_residual_hydro_creates_bloom_core(
    golden_assembled,
) -> None:
    assembled = golden_assembled(meta_name="burning golden")
    target_ref = target_subject()
    apply_aura(assembled, Element.DENDRO, "golden:burning-bloom:initial")
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.PYRO,
            "golden:burning-bloom:establish",
            strength=AuraStrength.STRONG,
            impact_key="golden.burning.application",
        ),
    )
    adjust = assembled.aura_runtime.begin_batch(0, "golden:burning-bloom:adjust")
    adjust.consume(
        interaction_id="golden:burning-bloom:adjust:burning",
        subject_ref=target_ref,
        aura_kind=AuraKind.BURNING,
        amount=AuraAmount(Fraction(3, 2)),
    )
    adjust.consume(
        interaction_id="golden:burning-bloom:adjust:pyro",
        subject_ref=target_ref,
        aura_kind=AuraKind.PYRO,
        amount=AuraAmount(Fraction(1, 10)),
    )
    assembled.aura_runtime.commit_prevalidated(adjust.seal())

    record = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.HYDRO,
            "golden:burning-bloom:hydro",
            strength=AuraStrength.STRONG,
            impact_key="golden.burning.application",
        ),
    )

    assert len(record.reaction_occurrence_refs) == 2
    assert len(assembled.reaction_runtime.active_dendro_cores()) == 1
    assert assembled.reaction_runtime.burning_state_for(target_ref) is None
    assert assembled.aura_runtime.view(target_ref).component_for(AuraKind.BURNING) is None


def _burning_records(assembled):
    return tuple(
        record
        for record in assembled.damage_handler.records
        if record.result.formula_key == FORMULA_KEY_TRANSFORMATIVE_REACTION
    )


def _burning_results(assembled):
    return tuple(record.result for record in _burning_records(assembled))


def _scheduled_roots(assembled):
    return tuple(
        record
        for record in assembled.elemental_settlement_coordinator.records
        if record.batch_kind.value == "scheduled_reaction_root"
    )
