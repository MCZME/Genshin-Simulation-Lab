from __future__ import annotations

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.systems.aura import (
    AuraComponent,
    AuraContribution,
    AuraContributionRef,
    AuraDecayMode,
    AuraInstanceRef,
    AuraStrength,
    AuraView,
)
from genshin_sim.core.systems.reaction import (
    CurrentImpactDamageAdjustment,
    GeneratedDamageImpactEffect,
    ReactionElementalApplication,
    ReactionEvaluationRequest,
    ReactionStateInstanceRef,
    ReactionTriggerContext,
    TransformativeSourceObservation,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.states import FrozenState

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")
LINK = ElementalStateLinkRef("elemental-state-link:test")


def test_shattered_precedes_pyro_reaction_with_exposed_hidden_hydro():
    frozen = FrozenState(
        ReactionStateInstanceRef("state:frozen"),
        TARGET,
        LINK,
        0,
    )
    request = ReactionEvaluationRequest(
        "interaction:shattered",
        "impact:target",
        0,
        0,
        SOURCE,
        TARGET,
        Element.PYRO,
        AuraAmount(1),
        AuraView(
            TARGET,
            (
                _ordinary_component(AuraKind.HYDRO, AuraAmount(1)),
                _frozen_component(AuraAmount(2)),
            ),
        ),
        current_damage_element=Element.PYRO,
        transformative_source_observation=_transformative_observation(),
        trigger_context=ReactionTriggerContext(
            elemental_application=ReactionElementalApplication(Element.PYRO, AuraAmount(1)),
            strike_type=StrikeType.BLUNT,
        ),
        observed_frozen_state=frozen,
    )

    resolution = create_default_reaction_bootstrap().create_runtime().evaluate(request)

    assert [
        occurrence.reaction_key
        for step in resolution.sequence.steps
        for occurrence in step.occurrences
    ] == ["reaction.shattered", "reaction.vaporize"]
    assert isinstance(resolution.damage_adjustment, CurrentImpactDamageAdjustment)
    assert resolution.damage_adjustment.base_multiplier == 1.5
    effect = resolution.effect_groups[0].effects[0]
    assert isinstance(effect, GeneratedDamageImpactEffect)
    assert effect.damage_kind_key == "reaction_damage.shattered"
    assert effect.transformative_base_multiplier == 3.0


def _ordinary_component(aura_kind: AuraKind, amount: AuraAmount) -> AuraComponent:
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
    )


def _frozen_component(amount: AuraAmount) -> AuraComponent:
    return AuraComponent(
        AuraInstanceRef("aura:frozen"),
        AuraKind.FROZEN,
        (
            AuraContribution(
                AuraContributionRef("contribution:frozen"),
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
        state_link_refs=(LINK,),
        decay_mode=AuraDecayMode.STATE_LINKED,
    )


def _transformative_observation() -> TransformativeSourceObservation:
    return TransformativeSourceObservation(
        SOURCE,
        TransformativeReactionSourceKind.CHARACTER,
        90,
        0.0,
        "character.level_multiplier.v1",
        1.0,
        "observation:source",
        1,
    )
