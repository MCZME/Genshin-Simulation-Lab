from __future__ import annotations

from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.coordination.elemental_reaction.capabilities import (
    ReactionCapabilityEvidence,
    ReactionEligibilityView,
)
from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraStrength
from genshin_sim.core.systems.damage import DamageScalingTerm
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_LUNAR_REACTION
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom.keys import (
    LUNAR_BLOOM_CAPABILITY_KEY,
)


class _TemporaryLunarEligibilityPort:
    def evidence_for(self, frame: int, team_ref: str) -> ReactionEligibilityView:
        return ReactionEligibilityView(
            team_ref=team_ref,
            frame=frame,
            evidence=(
                ReactionCapabilityEvidence(
                    LUNAR_BLOOM_CAPABILITY_KEY,
                    ElementalSubjectRef.character("character:slot_1"),
                ),
            ),
        )


def test_lunar_bloom_reaction_produces_no_reaction_damage(golden_assembled) -> None:
    assembled = golden_assembled(meta_name="lunar bloom no reaction damage", max_frames=1)
    assembled.elemental_interaction_coordinator.reaction_eligibility_port = (
        _TemporaryLunarEligibilityPort()
    )

    target_ref = ElementalSubjectRef.target("target:target_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "setup:lunar:dendro",
            "setup:lunar:dendro:application",
            "setup:lunar:dendro:impact",
            0,
            0,
            ElementalSourceRef("character:slot_1"),
            target_ref,
            Element.DENDRO,
            AuraStrength.WEAK,
        )
    )

    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        ImpactRequest(
            frame=0,
            kind=ImpactKind.DAMAGE,
            impact_key="golden:lunar:bloom",
            owner_slot=1,
            request_id="golden:lunar:bloom",
            target_refs=("target_1",),
            damage_spec=DamageImpactSpec(
                impact_ref="golden:lunar:bloom",
                main_attack_tag="testing.runtime_probe.direct",
                element=Element.HYDRO,
                scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
                can_crit=False,
                elemental_strength=AuraStrength.WEAK,
                elemental_amount=AuraAmount.one(),
            ),
        ),
    )

    assert any(
        event.event_type is EventType.REACTION_OCCURRED
        for event in assembled.context.events.frame_events
    )
    lunar_records = tuple(
        record
        for record in assembled.damage_handler.records
        if record.result.formula_key == FORMULA_KEY_LUNAR_REACTION
    )
    assert lunar_records == ()
    assert (
        assembled.reaction_runtime.lunar_bloom_dew_state_for(
            PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
            frame=0,
        )
        is not None
    )
