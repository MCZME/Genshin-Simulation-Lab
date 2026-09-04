from __future__ import annotations

from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraRuntime, AuraStrength
from genshin_sim.core.systems.reaction import (
    ReactionEvaluationRequest,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.electro_charged.mechanic import (
    ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_ELECTRO_CHARGED_CAPABILITY_KEY,
    LUNAR_ELECTRO_CHARGED_GATE_DEFINITION_KEY,
    LUNAR_ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.models import (
    TransformativeSourceObservation,
)

TARGET = ElementalSubjectRef.target("target:moon")
SOURCE_A = ElementalSourceRef("character:slot_1")
SOURCE_B = ElementalSourceRef("character:slot_2")
SOURCE_C = ElementalSourceRef("character:slot_3")
ENVIRONMENT = ElementalSourceRef("environment:rain")
CHARACTER_SOURCES = (SOURCE_A, SOURCE_B, SOURCE_C)


def _apply(
    runtime: AuraRuntime,
    source_ref: ElementalSourceRef,
    request_id: str,
    *,
    element: Element,
) -> None:
    runtime.apply(
        AuraApplicationRequest(
            request_id,
            f"{request_id}:application",
            f"impact:{request_id}",
            0,
            0,
            source_ref,
            TARGET,
            element,
            AuraStrength.WEAK,
        )
    )


def _observation(source_ref: ElementalSourceRef) -> TransformativeSourceObservation:
    return TransformativeSourceObservation(
        source_ref=source_ref,
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        elemental_mastery=0.0,
        level_multiplier_table_key="transformative.level_multipliers",
        level_multiplier=1.0,
        source_observation_ref=f"obs:{source_ref.source_key}",
        source_owner_slot=1,
    )


def _request(
    runtime: AuraRuntime,
    *,
    source_ref: ElementalSourceRef,
    incoming: Element,
    capability: bool = True,
    character_source_refs: tuple[ElementalSourceRef, ...] = CHARACTER_SOURCES,
) -> ReactionEvaluationRequest:
    return ReactionEvaluationRequest(
        "interaction:lunar-electro-charged",
        "impact:lunar-electro-charged",
        0,
        0,
        source_ref,
        TARGET,
        incoming,
        AuraAmount.one(),
        runtime.view(TARGET),
        transformative_source_observation=_observation(source_ref),
        character_source_refs=character_source_refs,
        reaction_capability_keys=(
            frozenset({LUNAR_ELECTRO_CHARGED_CAPABILITY_KEY}) if capability else frozenset()
        ),
    )


def test_lunar_electro_charged_is_exclusive_and_plans_storm_cloud() -> None:
    aura_runtime = AuraRuntime()
    _apply(aura_runtime, SOURCE_A, "aura:a", element=Element.ELECTRO)
    _apply(aura_runtime, SOURCE_B, "aura:b", element=Element.HYDRO)

    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(
            _request(
                aura_runtime,
                source_ref=ElementalSourceRef(SOURCE_C.source_key, "impact:character-c"),
                incoming=Element.HYDRO,
            )
        )
    )

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == LUNAR_ELECTRO_CHARGED_REACTION_KEY
    assert result.occurrence.participant_refs == (SOURCE_A, SOURCE_B, SOURCE_C)
    assert result.occurrence.lunar_storm_cloud_state_planning is not None
    assert result.occurrence.spatial_entity_creation is not None
    assert result.occurrence.effect_groups == ()
    assert result.occurrence.transition.aura_consumed == AuraAmount.zero()
    assert result.occurrence.transition.incoming_consumed == AuraAmount.zero()


def test_lunar_electro_charged_dedupes_same_character_contributions() -> None:
    aura_runtime = AuraRuntime()
    _apply(aura_runtime, SOURCE_A, "aura:a-hydro", element=Element.HYDRO)
    _apply(aura_runtime, SOURCE_A, "aura:a-electro", element=Element.ELECTRO)

    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(
            _request(
                aura_runtime,
                source_ref=SOURCE_C,
                incoming=Element.HYDRO,
            )
        )
    )

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == LUNAR_ELECTRO_CHARGED_REACTION_KEY
    assert result.occurrence.participant_refs == (SOURCE_A, SOURCE_C)


def test_lunar_electro_charged_falls_back_to_ordinary_electro_charged() -> None:
    aura_runtime = AuraRuntime()
    _apply(aura_runtime, SOURCE_A, "aura:ordinary", element=Element.ELECTRO)
    runtime = create_default_reaction_bootstrap().create_runtime()

    without_capability = runtime.evaluate(
        _request(
            aura_runtime,
            source_ref=SOURCE_C,
            incoming=Element.HYDRO,
            capability=False,
        )
    )
    environment_trigger = runtime.evaluate(
        _request(
            aura_runtime,
            source_ref=ENVIRONMENT,
            incoming=Element.HYDRO,
            character_source_refs=CHARACTER_SOURCES,
        )
    )

    assert without_capability.occurrence is not None
    assert without_capability.occurrence.reaction_key == ELECTRO_CHARGED_REACTION_KEY
    assert environment_trigger.occurrence is not None
    assert environment_trigger.occurrence.reaction_key == ELECTRO_CHARGED_REACTION_KEY


def test_default_bootstrap_registers_lunar_electro_charged_gate() -> None:
    gates = create_default_reaction_bootstrap().damage_gate_definitions
    gate = next(
        item
        for item in gates
        if item.gate_definition_key == LUNAR_ELECTRO_CHARGED_GATE_DEFINITION_KEY
    )
    assert gate.window_frames == 120
    assert gate.max_damage_instances == 1
