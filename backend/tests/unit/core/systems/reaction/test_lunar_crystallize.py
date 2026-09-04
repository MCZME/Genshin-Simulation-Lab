from __future__ import annotations

from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraRuntime, AuraStrength
from genshin_sim.core.systems.reaction import (
    ReactionEstablishmentGateDecision,
    ReactionEvaluationRequest,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.crystallize.mechanic import (
    CRYSTALLIZE_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize.keys import (
    LUNAR_CRYSTALLIZE_CAPABILITY_KEY,
    LUNAR_CRYSTALLIZE_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.models import CrystallizeSourceObservation

TARGET = ElementalSubjectRef.target("target:moon-crystallize")
SOURCE_A = ElementalSourceRef("character:slot_1")
SOURCE_B = ElementalSourceRef("character:slot_2")
ENVIRONMENT = ElementalSourceRef("environment:rock-fall")
CHARACTER_SOURCES = (SOURCE_A, SOURCE_B)


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


def _crystallize_observation(source_ref: ElementalSourceRef) -> CrystallizeSourceObservation:
    return CrystallizeSourceObservation(
        source_ref=source_ref,
        source_level=90,
        elemental_mastery=0.0,
    )


def _request(
    runtime: AuraRuntime,
    *,
    source_ref: ElementalSourceRef,
    incoming: Element,
    incoming_amount: AuraAmount | None = None,
    capability: bool = True,
    character_source_refs: tuple[ElementalSourceRef, ...] = CHARACTER_SOURCES,
) -> ReactionEvaluationRequest:
    return ReactionEvaluationRequest(
        "interaction:lunar-crystallize",
        "impact:lunar-crystallize",
        0,
        0,
        source_ref,
        TARGET,
        incoming,
        AuraAmount.one() if incoming_amount is None else incoming_amount,
        runtime.view(TARGET),
        crystallize_source_observation=_crystallize_observation(source_ref),
        character_source_refs=character_source_refs,
        reaction_capability_keys=(
            frozenset({LUNAR_CRYSTALLIZE_CAPABILITY_KEY}) if capability else frozenset()
        ),
    )


def test_lunar_crystallize_is_exclusive_and_plans_cages_and_accumulator() -> None:
    aura_runtime = AuraRuntime()
    _apply(aura_runtime, SOURCE_A, "aura:hydro", element=Element.HYDRO)

    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(
            _request(
                aura_runtime,
                source_ref=ElementalSourceRef(SOURCE_B.source_key, "impact:character-b"),
                incoming=Element.GEO,
            )
        )
    )

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == LUNAR_CRYSTALLIZE_REACTION_KEY
    assert result.occurrence.participant_refs == (SOURCE_A, SOURCE_B)
    intent = result.occurrence.lunar_crystallize_planning
    assert intent is not None
    assert len(intent.cage_instance_refs) == 3
    assert len(intent.cage_space_entity_refs) == 3
    assert result.occurrence.spatial_entity_creation is None
    assert result.occurrence.effect_groups == ()
    assert result.occurrence.transition.aura_consumed == AuraAmount("1/2")
    assert result.occurrence.transition.incoming_consumed == AuraAmount.one()


def test_lunar_crystallize_consumes_limited_by_hydro_aura() -> None:
    aura_runtime = AuraRuntime()
    _apply(aura_runtime, SOURCE_A, "aura:hydro-weak", element=Element.HYDRO)

    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(
            _request(
                aura_runtime,
                source_ref=SOURCE_B,
                incoming=Element.GEO,
            )
        )
    )

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == LUNAR_CRYSTALLIZE_REACTION_KEY
    weak = AuraAmount("1")
    assert result.occurrence.transition.aura_consumed == weak / 2
    assert result.occurrence.transition.incoming_consumed == weak


def test_lunar_crystallize_falls_back_to_ordinary_crystallize() -> None:
    runtime = create_default_reaction_bootstrap().create_runtime()

    without_capability_aura = AuraRuntime()
    _apply(without_capability_aura, SOURCE_A, "aura:hydro", element=Element.HYDRO)
    without_capability = runtime.evaluate(
        _request(
            without_capability_aura,
            source_ref=SOURCE_B,
            incoming=Element.GEO,
            capability=False,
        )
    )

    environment_aura = AuraRuntime()
    _apply(environment_aura, SOURCE_A, "aura:hydro", element=Element.HYDRO)
    environment_trigger = runtime.evaluate(
        _request(
            environment_aura,
            source_ref=ENVIRONMENT,
            incoming=Element.GEO,
            character_source_refs=CHARACTER_SOURCES,
        )
    )

    assert without_capability.occurrence is not None
    assert without_capability.occurrence.reaction_key == CRYSTALLIZE_REACTION_KEY
    assert environment_trigger.occurrence is not None
    assert environment_trigger.occurrence.reaction_key == CRYSTALLIZE_REACTION_KEY


def test_lunar_crystallize_does_not_replace_non_hydro_crystallize() -> None:
    aura_runtime = AuraRuntime()
    _apply(aura_runtime, SOURCE_A, "aura:pyro", element=Element.PYRO)

    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(
            _request(
                aura_runtime,
                source_ref=SOURCE_B,
                incoming=Element.GEO,
            )
        )
    )

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == CRYSTALLIZE_REACTION_KEY
    assert result.occurrence.lunar_crystallize_planning is None


def test_default_bootstrap_registers_lunar_crystallize() -> None:
    registry = create_default_reaction_bootstrap().reaction_registry
    assert registry.definition_for(LUNAR_CRYSTALLIZE_REACTION_KEY) is not None


def test_lunar_crystallize_replaces_hydro_candidate_in_water_electro_composite() -> None:
    aura_runtime = AuraRuntime()
    _apply(
        aura_runtime,
        SOURCE_A,
        "aura:composite-electro",
        element=Element.ELECTRO,
    )
    _apply(aura_runtime, SOURCE_A, "aura:composite-hydro", element=Element.HYDRO)

    resolution = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(
            _request(
                aura_runtime,
                source_ref=SOURCE_B,
                incoming=Element.GEO,
                incoming_amount=AuraAmount("3"),
            )
        )
    )

    occurrences = tuple(
        occurrence for step in resolution.sequence.steps for occurrence in step.occurrences
    )
    assert tuple(occurrence.reaction_key for occurrence in occurrences) == (
        CRYSTALLIZE_REACTION_KEY,
        LUNAR_CRYSTALLIZE_REACTION_KEY,
    )
    assert occurrences[0].direction_key == "incoming_geo_on_electro"
    assert occurrences[0].crystallize_shard_state_creation is not None
    assert occurrences[1].lunar_crystallize_planning is not None
    assert occurrences[1].crystallize_shard_state_creation is None


def test_lunar_crystallize_water_electro_without_capability_keeps_ordinary_hydro() -> None:
    aura_runtime = AuraRuntime()
    _apply(
        aura_runtime,
        SOURCE_A,
        "aura:composite-electro",
        element=Element.ELECTRO,
    )
    _apply(aura_runtime, SOURCE_A, "aura:composite-hydro", element=Element.HYDRO)

    resolution = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(
            _request(
                aura_runtime,
                source_ref=SOURCE_B,
                incoming=Element.GEO,
                incoming_amount=AuraAmount("3"),
                capability=False,
            )
        )
    )

    occurrences = tuple(
        occurrence for step in resolution.sequence.steps for occurrence in step.occurrences
    )
    assert tuple(occurrence.reaction_key for occurrence in occurrences) == (
        CRYSTALLIZE_REACTION_KEY,
        CRYSTALLIZE_REACTION_KEY,
    )
    assert tuple(occurrence.direction_key for occurrence in occurrences) == (
        "incoming_geo_on_electro",
        "incoming_geo_on_hydro",
    )


def test_lunar_crystallize_water_electro_gate_blocks_only_ordinary_hydro() -> None:
    runtime = create_default_reaction_bootstrap().create_runtime()
    aura_runtime = AuraRuntime()
    _apply(
        aura_runtime,
        SOURCE_A,
        "aura:composite-electro",
        element=Element.ELECTRO,
    )
    _apply(aura_runtime, SOURCE_A, "aura:composite-hydro", element=Element.HYDRO)

    planner = runtime.begin_batch(0, "lunar-crystallize-water-electro-gate")
    resolution = planner.prepare(
        _request(
            aura_runtime,
            source_ref=SOURCE_B,
            incoming=Element.GEO,
            incoming_amount=AuraAmount("3"),
        )
    )
    plan = planner.seal()

    occurrences = tuple(
        occurrence for step in resolution.sequence.steps for occurrence in step.occurrences
    )
    assert tuple(occurrence.reaction_key for occurrence in occurrences) == (
        CRYSTALLIZE_REACTION_KEY,
        LUNAR_CRYSTALLIZE_REACTION_KEY,
    )
    assert not resolution.establishment_gate_blocked
    assert plan.establishment_gate_plan is not None
    assert tuple(item.decision for item in plan.establishment_gate_plan.resolutions) == (
        ReactionEstablishmentGateDecision.ALLOWED,
    )

    blocked_runtime = create_default_reaction_bootstrap().create_runtime()
    blocked_aura = AuraRuntime()
    _apply(
        blocked_aura,
        SOURCE_A,
        "aura:composite-electro",
        element=Element.ELECTRO,
    )
    _apply(blocked_aura, SOURCE_A, "aura:composite-hydro", element=Element.HYDRO)
    blocked_planner = blocked_runtime.begin_batch(0, "ordinary-water-electro-gate")
    blocked_resolution = blocked_planner.prepare(
        _request(
            blocked_aura,
            source_ref=SOURCE_B,
            incoming=Element.GEO,
            incoming_amount=AuraAmount("3"),
            capability=False,
        )
    )
    blocked_occurrences = tuple(
        occurrence for step in blocked_resolution.sequence.steps for occurrence in step.occurrences
    )
    assert tuple(occurrence.direction_key for occurrence in blocked_occurrences) == (
        "incoming_geo_on_electro",
    )
    assert blocked_resolution.establishment_gate_blocked
