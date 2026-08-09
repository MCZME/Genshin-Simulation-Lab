from __future__ import annotations

from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.coordination.elemental_reaction.capabilities import (
    ReactionCapabilityEvidence,
    ReactionEligibilityView,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.damage import (
    DamageScalingTerm,
)
from genshin_sim.core.systems.reaction.mechanics.crystallize.mechanic import (
    CRYSTALLIZE_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize.keys import (
    LUNAR_CAGE_TEAM_SCOPE,
    LUNAR_CRYSTALLIZE_CAPABILITY_KEY,
    LUNAR_CRYSTALLIZE_REACTION_KEY,
)
from tests.helpers.reactions import apply_aura, lunar_damage_record_count, reaction_occurred_count


class _TemporaryLunarEligibilityPort:
    def evidence_for(self, frame: int, team_ref: str) -> ReactionEligibilityView:
        return ReactionEligibilityView(
            team_ref=team_ref,
            frame=frame,
            evidence=(
                ReactionCapabilityEvidence(
                    LUNAR_CRYSTALLIZE_CAPABILITY_KEY,
                    ElementalSubjectRef.character("character:slot_1"),
                ),
            ),
        )


def test_lunar_crystallize_accumulates_and_fires_harmony(golden_assembled) -> None:
    assembled = golden_assembled(meta_name="lunar crystallize harmony", max_frames=400)
    assembled.elemental_interaction_coordinator.reaction_eligibility_port = (
        _TemporaryLunarEligibilityPort()
    )

    target_ref = ElementalSubjectRef.target("target:target_1")
    hydro_source = ElementalSourceRef("character:slot_1")

    for order in range(3):
        apply_aura(
            assembled,
            Element.HYDRO,
            f"setup:hydro:{order}",
            frame=0,
            strength=AuraStrength.WEAK,
            target_ref=target_ref,
            source_ref=hydro_source,
        )
        assembled.elemental_settlement_coordinator.settle_damage_impact(
            assembled.context,
            _geo_impact(frame=0, request_id=f"golden:lunar:crystallize:trigger:{order}"),
        )

    assert reaction_occurred_count(assembled, LUNAR_CRYSTALLIZE_REACTION_KEY) == 3
    cages = assembled.reaction_runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)
    assert len(cages) == 3
    assert all(
        assembled.space_runtime.get_entity(cage.space_entity_ref) is not None for cage in cages
    )
    assert all(cage.next_attack_frame == 21 for cage in cages)
    assert all(cage.attack_index == 1 for cage in cages)
    assert (
        assembled.reaction_runtime.lunar_crystallize_accumulator_for(LUNAR_CAGE_TEAM_SCOPE) is None
    )
    assert lunar_damage_record_count(assembled) == 3

    for order in range(3, 6):
        apply_aura(
            assembled,
            Element.HYDRO,
            f"setup:hydro:{order}",
            frame=0,
            strength=AuraStrength.WEAK,
            target_ref=target_ref,
            source_ref=hydro_source,
        )
        assembled.elemental_settlement_coordinator.settle_damage_impact(
            assembled.context,
            _geo_impact(frame=0, request_id=f"golden:lunar:crystallize:trigger:{order}"),
        )
    assert reaction_occurred_count(assembled, LUNAR_CRYSTALLIZE_REACTION_KEY) == 6
    accumulator = assembled.reaction_runtime.lunar_crystallize_accumulator_for(
        LUNAR_CAGE_TEAM_SCOPE
    )
    assert accumulator is not None
    assert len(accumulator.pending_records) == 3
    assert lunar_damage_record_count(assembled) == 3

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 30)
    assert lunar_damage_record_count(assembled) == 3

    apply_aura(
        assembled,
        Element.HYDRO,
        "setup:hydro:6",
        frame=30,
        strength=AuraStrength.WEAK,
        target_ref=target_ref,
        source_ref=hydro_source,
    )
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _geo_impact(frame=30, request_id="golden:lunar:crystallize:trigger:6"),
    )
    assert reaction_occurred_count(assembled, LUNAR_CRYSTALLIZE_REACTION_KEY) == 7
    assert lunar_damage_record_count(assembled) == 6
    accumulator = assembled.reaction_runtime.lunar_crystallize_accumulator_for(
        LUNAR_CAGE_TEAM_SCOPE
    )
    assert accumulator is not None
    assert [item.occurrence_ref for item in accumulator.pending_records] == [
        "golden:lunar:crystallize:trigger:6:target:target_1:0:interaction:occurrence:0"
    ]
    cages = assembled.reaction_runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)
    assert all(cage.next_attack_frame == 51 for cage in cages)

    assert _aura_applied_count(assembled, Element.GEO) == 0
    hydro = assembled.aura_runtime.view(target_ref).component_for(AuraKind.HYDRO)
    assert hydro is not None
    assert not hydro.current_amount.is_zero


def test_lunar_crystallize_water_electro_composite_produces_shard_and_cages(
    golden_assembled,
) -> None:
    assembled = golden_assembled(meta_name="lunar crystallize harmony", max_frames=400)
    assembled.elemental_interaction_coordinator.reaction_eligibility_port = (
        _TemporaryLunarEligibilityPort()
    )
    target_ref = ElementalSubjectRef.target("target:target_1")
    source_ref = ElementalSourceRef("character:slot_1")

    apply_aura(
        assembled,
        Element.ELECTRO,
        "setup:composite:electro",
        frame=0,
        strength=AuraStrength.WEAK,
        target_ref=target_ref,
        source_ref=source_ref,
        application_coefficient=AuraAmount("1/2"),
    )
    apply_aura(
        assembled,
        Element.HYDRO,
        "setup:composite:hydro",
        frame=0,
        strength=AuraStrength.WEAK,
        target_ref=target_ref,
        source_ref=source_ref,
        application_coefficient=None,
    )
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _geo_impact(frame=0, request_id="golden:lunar:crystallize:composite"),
    )

    assert reaction_occurred_count(assembled, CRYSTALLIZE_REACTION_KEY) == 1
    assert reaction_occurred_count(assembled, LUNAR_CRYSTALLIZE_REACTION_KEY) == 1
    assert (
        len(
            [
                record
                for record in assembled.reaction_runtime.state_records
                if record.slot_key.slot.value == "crystallize_shard"
            ]
        )
        == 1
    )
    assert len(assembled.reaction_runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)) == 3


def _geo_impact(*, frame: int, request_id: str) -> ImpactRequest:
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.DAMAGE,
        impact_key="golden:lunar:crystallize",
        owner_slot=1,
        request_id=request_id,
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref=request_id,
            main_attack_tag="testing.runtime_probe.direct",
            element=Element.GEO,
            scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
            can_crit=False,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
        ),
    )


def _aura_applied_count(assembled, element: Element) -> int:
    return sum(
        1
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.AURA_APPLIED
        and event.payload.result.request.element is element
    )
