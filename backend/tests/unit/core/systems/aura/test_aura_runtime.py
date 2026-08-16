from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.systems.aura import (
    AuraApplicationProfile,
    AuraApplicationRequest,
    AuraDecayProfilePolicy,
    AuraRuntime,
    AuraStoreConflictError,
    AuraStrength,
    UnsupportedAuraCombinationError,
)

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")


def _request(request_id: str, frame: int = 0) -> AuraApplicationRequest:
    return AuraApplicationRequest(
        request_id,
        f"{request_id}:application",
        "impact:test",
        frame,
        0,
        SOURCE,
        TARGET,
        Element.HYDRO,
        AuraStrength.WEAK,
    )


def test_aura_amount_uses_exact_fraction_and_stable_serialization():
    amount = AuraAmount(Fraction(4, 5)) + AuraAmount(Fraction(1, 10))

    assert amount == AuraAmount(Fraction(9, 10))
    assert amount.to_dict() == {
        "numerator": 9,
        "denominator": 10,
        "decimal": 0.9,
    }


def test_same_element_application_uses_max_amount_and_exact_decay():
    runtime = AuraRuntime()

    created = runtime.apply(_request("aura:1"))
    assert created.after is not None
    assert created.after.current_amount == AuraAmount(Fraction(4, 5))

    runtime.update_frame(None, 60)
    decayed = runtime.view(TARGET).component_for(created.aura_kind)
    assert decayed is not None
    assert decayed.current_amount == AuraAmount(Fraction(68, 95))

    refreshed = runtime.apply(_request("aura:2", frame=60))
    assert refreshed.after is not None
    assert refreshed.after.current_amount == AuraAmount(Fraction(4, 5))


def test_regular_derived_profile_uses_emitted_raw_amount_for_natural_decay():
    runtime = AuraRuntime()
    raw_amount = AuraAmount(Fraction(11, 5))
    decay_profile = AuraApplicationProfile(
        profile_key="aura_application_profile.test.regular",
        decay_profile_policy=AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT,
    ).resolve_decay_profile(
        base_strength=AuraStrength.WEAK,
        effective_raw_amount=raw_amount,
    )
    created = runtime.apply(
        replace(
            _request("aura:derived"),
            effective_raw_amount=raw_amount,
            decay_profile=decay_profile,
        )
    )

    assert created.after is not None
    assert created.after.current_amount == AuraAmount(Fraction(44, 25))
    assert created.after.resolved_decay_profile == decay_profile

    runtime.update_frame(None, 60)

    component = runtime.view(TARGET).component_for(AuraKind.HYDRO)
    assert component is not None
    assert component.current_amount == AuraAmount(Fraction(1012, 625))

    runtime.update_frame(None, 750)

    assert not runtime.view(TARGET).components


def test_derived_decay_profile_rejects_a_different_effective_raw_amount():
    raw_amount = AuraAmount(Fraction(11, 5))
    decay_profile = AuraApplicationProfile(
        profile_key="aura_application_profile.test.regular",
        decay_profile_policy=AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT,
    ).resolve_decay_profile(
        base_strength=AuraStrength.WEAK,
        effective_raw_amount=raw_amount,
    )

    with pytest.raises(ValueError, match="同一原始元素量"):
        replace(
            _request("aura:mismatched-derived"),
            effective_raw_amount=AuraAmount(Fraction(39, 20)),
            decay_profile=decay_profile,
        )


def test_reaction_transition_consumes_exact_amount_without_persisting_incoming_residual():
    runtime = AuraRuntime()
    runtime.apply(_request("aura:1"))
    planner = runtime.begin_batch(0, "reaction")

    result = planner.consume(
        interaction_id="interaction:1",
        subject_ref=TARGET,
        aura_kind=AuraKind.HYDRO,
        amount=AuraAmount(Fraction(1, 2)),
    )
    runtime.commit_prevalidated(planner.seal())

    assert result.amount_before == AuraAmount(Fraction(4, 5))
    assert result.amount_consumed == AuraAmount(Fraction(1, 2))
    assert result.amount_after == AuraAmount(Fraction(3, 10))
    component = runtime.view(TARGET).component_for(AuraKind.HYDRO)
    assert component is not None
    assert component.current_amount == AuraAmount(Fraction(3, 10))


def test_aura_transition_rejects_duplicate_committed_interaction_id():
    runtime = AuraRuntime()
    runtime.apply(_request("aura:1"))
    first = runtime.begin_batch(0, "reaction:first")
    first.consume(
        interaction_id="interaction:once",
        subject_ref=TARGET,
        aura_kind=AuraKind.HYDRO,
        amount=AuraAmount(Fraction(1, 2)),
    )
    runtime.commit_prevalidated(first.seal())

    retry = runtime.begin_batch(0, "reaction:retry")
    retry.consume(
        interaction_id="interaction:once",
        subject_ref=TARGET,
        aura_kind=AuraKind.HYDRO,
        amount=AuraAmount(Fraction(1, 2)),
    )

    with pytest.raises(AuraStoreConflictError, match="重复的 Aura 交互"):
        runtime.commit_prevalidated(retry.seal())

    component = runtime.view(TARGET).component_for(AuraKind.HYDRO)
    assert component is not None
    assert component.current_amount == AuraAmount(Fraction(3, 10))


def test_unsupported_different_aura_is_rejected_without_creating_a_second_component():
    runtime = AuraRuntime()
    runtime.apply(_request("aura:hydro"))

    with pytest.raises(UnsupportedAuraCombinationError, match="不支持 hydro 与 cryo"):
        runtime.apply(
            AuraApplicationRequest(
                "aura:cryo",
                "aura:cryo:application",
                "impact:test",
                0,
                1,
                SOURCE,
                TARGET,
                Element.CRYO,
                AuraStrength.WEAK,
            )
        )

    components = runtime.view(TARGET).components
    assert len(components) == 1
    assert components[0].aura_kind is AuraKind.HYDRO


def test_uncommitted_plan_does_not_consume_stable_aura_identity_sequence():
    runtime = AuraRuntime()
    discarded = runtime.begin_batch(0, "discarded")
    discarded.apply(_request("aura:discarded"))

    committed = runtime.apply(_request("aura:committed"))

    assert committed.after is not None
    assert committed.after.instance_ref.value == "aura-instance:1"
    assert committed.after.contributions[0].contribution_ref.value == "aura-contribution:1"


def test_aura_plan_captures_store_version_when_batch_starts():
    runtime = AuraRuntime()
    planned = runtime.begin_batch(0, "planned")
    planned.apply(_request("aura:planned"))
    runtime.apply(_request("aura:committed"))

    with pytest.raises(AuraStoreConflictError, match="已经过期"):
        runtime.commit_prevalidated(planned.seal())


def test_aura_batch_rejects_duplicate_order():
    runtime = AuraRuntime()
    planner = runtime.begin_batch(0, "duplicate-order")
    planner.apply(_request("aura:first"))

    with pytest.raises(ValueError, match="重复的 Aura order：0"):
        planner.apply(
            replace(
                _request("aura:second"),
                application_id="aura:second:application",
            )
        )


def test_natural_aura_depletion_publishes_committed_fact():
    context = SimulationContext()
    runtime = AuraRuntime()
    events = []
    context.events.subscribe(EventType.AURA_DEPLETED, events.append)
    runtime.apply(_request("aura:1"))

    runtime.update_frame(context, 570)

    assert not runtime.view(TARGET).components
    assert [event.event_type for event in events] == [EventType.AURA_DEPLETED]
    assert events[0].payload.result.amount_before == AuraAmount(Fraction(4, 5))
    assert events[0].payload.result.amount_after == AuraAmount.zero()
