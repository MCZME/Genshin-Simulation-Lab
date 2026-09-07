from __future__ import annotations

from fractions import Fraction

import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraRuntime, AuraStrength
from genshin_sim.core.systems.reaction import (
    ReactionEvaluationRequest,
    ReactionRuntime,
    ReactionStoreMutationPlan,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.bloom.keys import (
    BLOOM_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom.keys import (
    LUNAR_BLOOM_CAPABILITY_KEY,
    LUNAR_BLOOM_REACTION_KEY,
)

TARGET = ElementalSubjectRef.target("target:moon")
SOURCE_A = ElementalSourceRef("character:slot_1")
SOURCE_B = ElementalSourceRef("character:slot_2")
SOURCE_C = ElementalSourceRef("character:slot_3")
ENVIRONMENT = ElementalSourceRef("environment:rain")
CHARACTER_SOURCES = (SOURCE_A, SOURCE_B, SOURCE_C)


def _apply_dendro(runtime: AuraRuntime, source_ref: ElementalSourceRef, request_id: str) -> None:
    runtime.apply(
        AuraApplicationRequest(
            request_id,
            f"{request_id}:application",
            f"impact:{request_id}",
            0,
            0,
            source_ref,
            TARGET,
            Element.DENDRO,
            AuraStrength.WEAK,
        )
    )


def _request(
    runtime: AuraRuntime,
    *,
    source_ref: ElementalSourceRef,
    capability: bool = True,
    character_source_refs: tuple[ElementalSourceRef, ...] = CHARACTER_SOURCES,
) -> ReactionEvaluationRequest:
    return ReactionEvaluationRequest(
        "interaction:lunar-bloom",
        "impact:lunar-bloom",
        0,
        0,
        source_ref,
        TARGET,
        Element.HYDRO,
        AuraAmount.one(),
        runtime.view(TARGET),
        character_source_refs=character_source_refs,
        reaction_capability_keys=(
            frozenset({LUNAR_BLOOM_CAPABILITY_KEY}) if capability else frozenset()
        ),
    )


def _commit_resource_batch(
    runtime: ReactionRuntime,
    *,
    frame: int,
    batch_id: str,
    refresh: bool,
    consume: int | None = None,
) -> None:
    gate_plan = runtime.begin_gate_batch(frame, f"{batch_id}:gate").seal()
    state_plan = runtime.begin_state_batch(frame, f"{batch_id}:state").seal()
    resource_planner = runtime.begin_resource_batch(frame, batch_id)
    if refresh:
        resource_planner.refresh_lunar_bloom_dew(
            team_ref=PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
        )
    if consume is not None:
        resource_planner.consume_lunar_bloom_dew(
            team_ref=PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
            amount=consume,
        )
    resource_plan = resource_planner.seal()
    runtime.commit_prevalidated_store_mutation_plan(
        ReactionStoreMutationPlan(
            gate_plan,
            state_plan,
            resource_plan=resource_plan,
        )
    )


def test_lunar_bloom_is_exclusive_and_freezes_all_character_participants() -> None:
    aura_runtime = AuraRuntime()
    _apply_dendro(aura_runtime, SOURCE_A, "aura:a")
    _apply_dendro(aura_runtime, SOURCE_B, "aura:b")

    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(
            _request(
                aura_runtime,
                source_ref=ElementalSourceRef(SOURCE_C.source_key, "impact:character-c"),
            )
        )
    )

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == LUNAR_BLOOM_REACTION_KEY
    assert result.occurrence.participant_refs == (SOURCE_A, SOURCE_B, SOURCE_C)
    assert result.occurrence.dendro_core_state_creation is not None
    assert result.occurrence.dendro_core_state_creation.pool_scope == (
        PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE
    )
    assert result.occurrence.effect_groups == ()


def test_lunar_bloom_falls_back_to_ordinary_for_missing_capability_or_non_character_source() -> (
    None
):
    aura_runtime = AuraRuntime()
    _apply_dendro(aura_runtime, SOURCE_A, "aura:ordinary")
    runtime = create_default_reaction_bootstrap().create_runtime()

    without_capability = runtime.evaluate(
        _request(aura_runtime, source_ref=SOURCE_C, capability=False)
    )
    environment_trigger = runtime.evaluate(
        _request(
            aura_runtime,
            source_ref=ENVIRONMENT,
            character_source_refs=CHARACTER_SOURCES,
        )
    )

    assert without_capability.occurrence is not None
    assert without_capability.occurrence.reaction_key == BLOOM_REACTION_KEY
    assert environment_trigger.occurrence is not None
    assert environment_trigger.occurrence.reaction_key == BLOOM_REACTION_KEY


def test_lunar_bloom_dew_refresh_preserves_progress_and_caps_at_three() -> None:
    runtime = create_default_reaction_bootstrap().create_runtime()
    _commit_resource_batch(runtime, frame=0, batch_id="dew:0", refresh=True)
    assert runtime.lunar_bloom_dew_state_for(PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE) is not None
    progressed = runtime.lunar_bloom_dew_state_for(
        PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
        frame=75,
    )
    assert progressed is not None
    assert progressed.current_value == Fraction(1, 2)

    runtime.update_frame(None, 150)
    _commit_resource_batch(runtime, frame=150, batch_id="dew:150", refresh=True)
    refreshed = runtime.lunar_bloom_dew_state_for(
        PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
        frame=150,
    )
    assert refreshed is not None
    assert refreshed.current_value == Fraction(1)
    assert refreshed.recovery_expires_at_frame == 300

    runtime.update_frame(None, 300)
    _commit_resource_batch(runtime, frame=300, batch_id="dew:300", refresh=True)
    runtime.update_frame(None, 450)
    _commit_resource_batch(runtime, frame=450, batch_id="dew:450", refresh=True)
    capped = runtime.lunar_bloom_dew_state_for(
        PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
        frame=600,
    )
    assert capped is not None
    assert capped.current_value == Fraction(3)
    assert capped.current_value <= capped.capacity


def test_lunar_bloom_dew_consumption_requires_integer_and_enough_dew() -> None:
    runtime = create_default_reaction_bootstrap().create_runtime()
    _commit_resource_batch(runtime, frame=0, batch_id="dew:consume:0", refresh=True)

    planner = runtime.begin_resource_batch(0, "consume:invalid")
    with pytest.raises(ValueError, match="正整数"):
        planner.consume_lunar_bloom_dew(
            team_ref=PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
            amount=0,
        )
    with pytest.raises(ValueError, match="正整数"):
        planner.consume_lunar_bloom_dew(
            team_ref=PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
            amount=True,
        )
    with pytest.raises(ValueError, match="草露不足"):
        _commit_resource_batch(
            runtime,
            frame=0,
            batch_id="consume:insufficient",
            refresh=False,
            consume=1,
        )


def test_lunar_bloom_dew_consumption_preserves_recovery_window() -> None:
    runtime = create_default_reaction_bootstrap().create_runtime()
    _commit_resource_batch(runtime, frame=0, batch_id="dew:consume:0", refresh=True)
    runtime.update_frame(None, 150)
    _commit_resource_batch(runtime, frame=150, batch_id="dew:consume:150", refresh=True)
    _commit_resource_batch(
        runtime,
        frame=150,
        batch_id="consume:1",
        refresh=False,
        consume=1,
    )

    consumed = runtime.lunar_bloom_dew_state_for(
        PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
        frame=150,
    )
    assert consumed is not None
    assert consumed.current_value == Fraction(0)
    assert consumed.recovery_expires_at_frame == 300

    runtime.update_frame(None, 300)
    recovered = runtime.lunar_bloom_dew_state_for(
        PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
        frame=300,
    )
    assert recovered is not None
    assert recovered.current_value == Fraction(1)
