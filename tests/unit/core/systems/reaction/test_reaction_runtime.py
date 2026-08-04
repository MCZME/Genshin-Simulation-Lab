from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraRuntime, AuraStrength
from genshin_sim.core.systems.reaction import (
    CapturedTransformativeScalingBasis,
    CurrentImpactDamageAdjustment,
    GeneratedDamageImpactEffect,
    ReactionEvaluationRequest,
    create_default_reaction_bootstrap,
)

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")


@pytest.mark.parametrize(
    (
        "aura_element",
        "incoming",
        "expected_reaction",
        "expected_multiplier",
        "incoming_used",
        "aura_used",
    ),
    [
        (Element.HYDRO, Element.PYRO, "reaction.vaporize", 1.5, Fraction(1, 1), Fraction(1, 2)),
        (Element.PYRO, Element.HYDRO, "reaction.vaporize", 2.0, Fraction(2, 5), Fraction(4, 5)),
        (Element.CRYO, Element.PYRO, "reaction.melt", 2.0, Fraction(2, 5), Fraction(4, 5)),
        (Element.PYRO, Element.CRYO, "reaction.melt", 1.5, Fraction(1, 1), Fraction(1, 2)),
    ],
)
def test_vaporize_and_melt_use_confirmed_exact_consumption(
    aura_element: Element,
    incoming: Element,
    expected_reaction: str,
    expected_multiplier: float,
    incoming_used: Fraction,
    aura_used: Fraction,
):
    aura_runtime = AuraRuntime()
    aura_runtime.apply(
        AuraApplicationRequest(
            "aura:1",
            "application:1",
            "impact:aura",
            0,
            0,
            SOURCE,
            TARGET,
            aura_element,
            AuraStrength.WEAK,
        )
    )
    request = ReactionEvaluationRequest(
        "interaction:1",
        "impact:target:1",
        0,
        0,
        SOURCE,
        TARGET,
        incoming,
        AuraAmount.one(),
        aura_runtime.view(TARGET),
        incoming,
    )

    result = create_default_reaction_bootstrap().create_runtime().evaluate(request)

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == expected_reaction
    assert result.occurrence.transition.incoming_consumed == AuraAmount(incoming_used)
    assert result.occurrence.transition.aura_consumed == AuraAmount(aura_used)
    assert isinstance(result.damage_adjustment, CurrentImpactDamageAdjustment)
    assert result.damage_adjustment.base_multiplier == expected_multiplier
    assert result.decision_sequence is not None
    assert result.decision_sequence.steps[0].selected_candidate_keys == (expected_reaction,)


def test_reaction_batch_rejects_duplicate_order():
    runtime = create_default_reaction_bootstrap().create_runtime()
    request = ReactionEvaluationRequest(
        "interaction:first",
        "impact:target:1",
        0,
        0,
        SOURCE,
        TARGET,
        Element.HYDRO,
        AuraAmount.one(),
        AuraRuntime().view(TARGET),
    )
    planner = runtime.begin_batch(0, "duplicate-order")
    planner.prepare(request)

    with pytest.raises(ValueError, match="重复的 Reaction order：0"):
        planner.prepare(replace(request, interaction_id="interaction:second"))


@pytest.mark.parametrize(
    (
        "aura_element",
        "incoming",
        "expected_reaction",
        "expected_multiplier",
        "expected_strike_type",
    ),
    (
        (Element.ELECTRO, Element.PYRO, "reaction.overloaded", 2.75, StrikeType.BLUNT),
        (Element.PYRO, Element.ELECTRO, "reaction.overloaded", 2.75, StrikeType.BLUNT),
        (Element.ELECTRO, Element.CRYO, "reaction.superconduct", 1.5, None),
        (Element.CRYO, Element.ELECTRO, "reaction.superconduct", 1.5, None),
    ),
)
def test_transformative_reaction_effect_carries_profile_multiplier(
    aura_element: Element,
    incoming: Element,
    expected_reaction: str,
    expected_multiplier: float,
    expected_strike_type: StrikeType | None,
):
    aura_runtime = AuraRuntime()
    aura_runtime.apply(
        AuraApplicationRequest(
            "aura:initial",
            "application:initial",
            "impact:initial",
            0,
            0,
            SOURCE,
            TARGET,
            aura_element,
            AuraStrength.WEAK,
        )
    )
    basis = CapturedTransformativeScalingBasis(
        basis_ref="basis:periodic",
        captured_frame=0,
        source_ref=SOURCE,
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        elemental_mastery=120.0,
        reaction_bonus=0.0,
        reaction_profile_key="reaction_profile.periodic",
        damage_profile_key="damage_profile.reaction.overloaded",
        level_multiplier_table_key="character",
        level_multiplier=1446.853,
        source_observation_ref="observation:periodic",
        source_owner_slot=1,
    )
    request = ReactionEvaluationRequest(
        "interaction:periodic",
        "impact:periodic",
        15,
        0,
        SOURCE,
        TARGET,
        incoming,
        AuraAmount.one(),
        aura_runtime.view(TARGET),
        transformative_source_observation=basis,
    )

    result = create_default_reaction_bootstrap().create_runtime().evaluate(request)

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == expected_reaction
    effect = result.occurrence.effect_groups[0].effects[0]
    assert isinstance(effect, GeneratedDamageImpactEffect)
    assert effect.captured_scaling_basis.source_ref == SOURCE
    assert effect.transformative_base_multiplier == expected_multiplier
    assert effect.strike_type is expected_strike_type
