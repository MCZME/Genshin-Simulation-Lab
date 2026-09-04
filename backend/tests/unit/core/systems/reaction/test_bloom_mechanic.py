from __future__ import annotations

from fractions import Fraction

import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraRuntime, AuraStrength
from genshin_sim.core.systems.reaction import (
    BloomReactionProfile,
    DynamicTransformativeScalingBasis,
    ReactionEvaluationRequest,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.bloom.keys import (
    BLOOM_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    DENDRO_CORE_STATE_KEY,
)

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")


@pytest.mark.parametrize(
    ("aura_element", "incoming_element", "expected_incoming", "expected_aura"),
    (
        (Element.DENDRO, Element.HYDRO, Fraction(1), Fraction(1, 2)),
        (Element.HYDRO, Element.DENDRO, Fraction(2, 5), Fraction(4, 5)),
    ),
)
def test_bloom_uses_confirmed_two_to_one_consumption_and_declares_core(
    aura_element: Element,
    incoming_element: Element,
    expected_incoming: Fraction,
    expected_aura: Fraction,
) -> None:
    aura_runtime = AuraRuntime()
    aura_runtime.apply(
        AuraApplicationRequest(
            "aura:seed",
            "application:seed",
            "impact:seed",
            0,
            0,
            SOURCE,
            TARGET,
            aura_element,
            AuraStrength.WEAK,
        )
    )
    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(
            ReactionEvaluationRequest(
                "interaction:bloom",
                "impact:bloom",
                0,
                0,
                SOURCE,
                TARGET,
                incoming_element,
                AuraAmount.one(),
                aura_runtime.view(TARGET),
            )
        )
    )

    occurrence = result.occurrence
    assert occurrence is not None
    assert occurrence.reaction_key == BLOOM_REACTION_KEY
    assert occurrence.transition.incoming_consumed == AuraAmount(expected_incoming)
    assert occurrence.transition.aura_consumed == AuraAmount(expected_aura)
    intent = occurrence.dendro_core_state_creation
    assert intent is not None
    assert intent.expires_at_frame == 360
    assert intent.creation_sequence == 0
    assert isinstance(intent.dynamic_scaling_basis, DynamicTransformativeScalingBasis)
    assert intent.dynamic_scaling_basis.source_ref == SOURCE
    assert occurrence.spatial_entity_creation is not None
    assert DENDRO_CORE_STATE_KEY in occurrence.spatial_entity_creation.tags


def test_bloom_profiles_cover_quicken_as_dendro_like_aura() -> None:
    registry = create_default_reaction_bootstrap().reaction_registry
    definition = registry.definition_for(BLOOM_REACTION_KEY)

    profiles = tuple(
        profile for profile in definition.profiles if isinstance(profile, BloomReactionProfile)
    )

    assert {profile.dendro_like_kind for profile in profiles} == {
        AuraKind.DENDRO,
        AuraKind.HYDRO,
        AuraKind.QUICKEN,
    }
