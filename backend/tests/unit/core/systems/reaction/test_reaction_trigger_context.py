from __future__ import annotations

import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
)
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraRuntime,
    AuraStrength,
    FrozenAuraApplicationRequest,
)
from genshin_sim.core.systems.reaction import (
    FrozenState,
    ReactionDefinition,
    ReactionElementalApplication,
    ReactionEntryKind,
    ReactionEvaluationRequest,
    ReactionRegistry,
    ReactionResolution,
    ReactionRuntime,
    ReactionSelectionError,
    ReactionStateInstanceRef,
    ReactionTriggerContext,
    create_default_reaction_bootstrap,
)


class _StateTriggerProbe:
    def __init__(self) -> None:
        self.requests: list[ReactionEvaluationRequest] = []

    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution:
        self.requests.append(request)
        return ReactionResolution(request, None, None)


def test_blunt_zero_element_amount_is_a_valid_state_trigger_context_without_production_rule():
    target = ElementalSubjectRef.target("target:target_1")
    request = ReactionEvaluationRequest(
        "interaction:blunt",
        "impact:target:blunt",
        0,
        0,
        ElementalSourceRef("character:slot_1"),
        target,
        None,
        AuraAmount.zero(),
        AuraRuntime().view(target),
        trigger_context=ReactionTriggerContext(strike_type=StrikeType.BLUNT),
    )

    resolution = create_default_reaction_bootstrap().create_runtime().evaluate(request)

    assert resolution.occurrence is None
    assert request.trigger_context is not None
    assert request.trigger_context.strike_type is StrikeType.BLUNT


def test_reaction_trigger_context_rejects_empty_evidence():
    with pytest.raises(ValueError, match="至少需要元素施加或打击证据"):
        ReactionTriggerContext()


def test_state_trigger_candidate_receives_elemental_blunt_context():
    target = ElementalSubjectRef.target("target:target_1")
    probe = _StateTriggerProbe()
    runtime = ReactionRuntime(
        ReactionRegistry(
            (
                ReactionDefinition(
                    "reaction.test.state_trigger",
                    "reaction_handler.test.state_trigger",
                    (),
                    (),
                    probe,
                    ReactionEntryKind.STATE_TRIGGER,
                ),
            )
        )
    )
    request = ReactionEvaluationRequest(
        "interaction:elemental-blunt",
        "impact:target:elemental-blunt",
        0,
        0,
        ElementalSourceRef("character:slot_1"),
        target,
        Element.PYRO,
        AuraAmount.one(),
        AuraRuntime().view(target),
        trigger_context=ReactionTriggerContext(
            elemental_application=ReactionElementalApplication(Element.PYRO, AuraAmount.one()),
            strike_type=StrikeType.BLUNT,
        ),
    )

    runtime.evaluate(request)

    assert probe.requests == [request]


def test_frozen_state_observation_requires_matching_frozen_aura_link():
    target = ElementalSubjectRef.target("target:target_1")
    source = ElementalSourceRef("character:slot_1")
    link = ElementalStateLinkRef("elemental-state-link:matching")
    aura_runtime = AuraRuntime()
    aura_planner = aura_runtime.begin_batch(0, "frozen-observation")
    aura_planner.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen",
            "application:frozen",
            "impact:frozen",
            0,
            0,
            source,
            target,
            link,
            AuraAmount(2),
        )
    )
    aura_runtime.commit_prevalidated(aura_planner.seal())
    state = FrozenState(
        ReactionStateInstanceRef("reaction-state-instance:1"),
        target,
        link,
        0,
    )

    request = ReactionEvaluationRequest(
        "interaction:frozen",
        "impact:target:frozen",
        0,
        0,
        source,
        target,
        None,
        AuraAmount.zero(),
        aura_runtime.view(target),
        trigger_context=ReactionTriggerContext(strike_type=StrikeType.BLUNT),
        observed_frozen_state=state,
    )

    assert request.has_active_frozen_state
    with pytest.raises(ValueError, match="冻元素 Aura Link 一致"):
        ReactionEvaluationRequest(
            "interaction:mismatched-frozen",
            "impact:target:mismatched-frozen",
            0,
            0,
            source,
            target,
            None,
            AuraAmount.zero(),
            aura_runtime.view(target),
            trigger_context=ReactionTriggerContext(strike_type=StrikeType.BLUNT),
            observed_frozen_state=FrozenState(
                ReactionStateInstanceRef("reaction-state-instance:2"),
                target,
                ElementalStateLinkRef("elemental-state-link:mismatched"),
                0,
            ),
        )


def test_hybrid_state_and_elemental_candidates_fail_without_confirmed_sequence_relation():
    target = ElementalSubjectRef.target("target:target_1")
    source = ElementalSourceRef("character:slot_1")
    aura_runtime = AuraRuntime()
    aura_runtime.apply(
        AuraApplicationRequest(
            "aura:hydro",
            "application:hydro",
            "impact:hydro",
            0,
            0,
            source,
            target,
            Element.HYDRO,
            AuraStrength.WEAK,
        )
    )
    probe = _StateTriggerProbe()
    state_definition = ReactionDefinition(
        "reaction.test.state_trigger",
        "reaction_handler.test.state_trigger",
        (),
        (),
        probe,
        ReactionEntryKind.STATE_TRIGGER,
    )
    base_definitions = create_default_reaction_bootstrap().reaction_registry.definitions
    runtime = ReactionRuntime(ReactionRegistry((*base_definitions, state_definition)))
    request = ReactionEvaluationRequest(
        "interaction:hybrid",
        "impact:target:hybrid",
        0,
        0,
        source,
        target,
        Element.PYRO,
        AuraAmount.one(),
        aura_runtime.view(target),
        trigger_context=ReactionTriggerContext(
            elemental_application=ReactionElementalApplication(Element.PYRO, AuraAmount.one()),
            strike_type=StrikeType.BLUNT,
        ),
    )

    with pytest.raises(ReactionSelectionError, match="候选存在歧义"):
        runtime.evaluate(request)

    assert probe.requests == [request]
