from __future__ import annotations

import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import (
    AuraComponent,
    AuraContribution,
    AuraContributionRef,
    AuraInstanceRef,
    AuraStrength,
    AuraView,
)
from genshin_sim.core.systems.reaction import (
    ReactionEvaluationRequest,
    ReactionRuntime,
    ReactionTriggerSignature,
)
from genshin_sim.core.systems.reaction.mechanics.frozen import frozen_definition
from genshin_sim.core.systems.reaction.runtime import ReactionRegistry

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")


@pytest.mark.parametrize(
    ("incoming", "aura_kind", "expected_direction"),
    (
        (Element.HYDRO, AuraKind.CRYO, "incoming_hydro_on_cryo"),
        (Element.CRYO, AuraKind.HYDRO, "incoming_cryo_on_hydro"),
    ),
)
def test_frozen_definition_consumes_the_smaller_water_or_cryo_amount(
    incoming: Element,
    aura_kind: AuraKind,
    expected_direction: str,
):
    component = AuraComponent(
        AuraInstanceRef("aura:1"),
        aura_kind,
        (
            AuraContribution(
                AuraContributionRef("contribution:1"),
                SOURCE,
                AuraAmount("0.7"),
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
    request = ReactionEvaluationRequest(
        "interaction:frozen",
        "impact:target",
        0,
        0,
        SOURCE,
        TARGET,
        incoming,
        AuraAmount(1),
        AuraView(TARGET, (component,)),
    )

    resolution = ReactionRuntime(ReactionRegistry((frozen_definition(),))).evaluate(request)

    assert resolution.occurrence is not None
    assert resolution.occurrence.reaction_key == "reaction.frozen"
    assert resolution.occurrence.direction_key == expected_direction
    assert resolution.occurrence.transition.incoming_consumed == AuraAmount("0.7")
    assert resolution.occurrence.transition.aura_consumed == AuraAmount("0.7")
    assert resolution.occurrence.transition.incoming_remaining == AuraAmount("0.3")


def test_frozen_definition_has_the_two_stable_water_cryo_signatures():
    definition = frozen_definition()

    assert definition.reaction_key == "reaction.frozen"
    assert definition.handler_key == "reaction_handler.frozen"
    assert definition.trigger_signatures == (
        ReactionTriggerSignature(Element.HYDRO, AuraKind.CRYO, "incoming_hydro_on_cryo"),
        ReactionTriggerSignature(Element.CRYO, AuraKind.HYDRO, "incoming_cryo_on_hydro"),
    )
