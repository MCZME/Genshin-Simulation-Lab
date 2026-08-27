# 单一关注点：结晶机制。
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

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
    CrystallizeSourceObservation,
    ReactionElementalApplication,
    ReactionEstablishmentGateDecision,
    ReactionEvaluationRequest,
    ReactionRegistry,
    ReactionRuntime,
    ReactionStateInstanceRef,
    ReactionTriggerContext,
    TransformativeSourceObservation,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.crystallize import (
    CrystallizeLevelOutOfRangeError,
    capture_crystallize_shield_basis,
    crystallize_definition,
    crystallize_establishment_gate_definition,
    crystallize_level_coefficient,
    elemental_mastery_bonus,
)
from genshin_sim.core.systems.reaction.states import FrozenState

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")

_EXPECTED_LEVEL_COEFFICIENTS = (
    91.179,
    98.707,
    106.236,
    113.764,
    121.293,
    128.821,
    136.350,
    143.878,
    151.407,
    158.936,
    169.991,
    181.076,
    192.190,
    204.048,
    215.938,
    227.862,
    247.685,
    267.542,
    287.431,
    303.826,
    320.225,
    336.627,
    352.319,
    368.010,
    383.702,
    394.432,
    405.181,
    415.949,
    426.737,
    437.544,
    450.600,
    463.700,
    476.845,
    491.127,
    502.554,
    514.012,
    531.409,
    549.979,
    568.584,
    584.996,
    605.670,
    626.386,
    646.052,
    665.755,
    685.496,
    700.839,
    723.333,
    745.865,
    768.435,
    786.791,
    809.538,
    832.329,
    855.162,
    878.039,
    899.484,
    919.361,
    946.039,
    974.764,
    1003.578,
    1030.077,
    1056.635,
    1085.246,
    1113.924,
    1149.258,
    1178.064,
    1200.223,
    1227.660,
    1257.243,
    1284.917,
    1314.752,
    1342.665,
    1372.752,
    1396.321,
    1427.312,
    1458.374,
    1482.335,
    1511.910,
    1541.549,
    1569.153,
    1596.814,
    1622.419,
    1648.073,
    1666.376,
    1684.678,
    1702.980,
    1726.104,
    1754.671,
    1785.866,
    1817.137,
    1851.060,
    1885.067,
    1921.749,
    1958.523,
    2006.194,
    2041.568,
    2054.472,
    2065.975,
    2174.722,
    2186.768,
    2198.813,
)


@pytest.mark.parametrize(
    ("aura_kind", "shard_element", "direction"),
    (
        (AuraKind.PYRO, Element.PYRO, "incoming_geo_on_pyro"),
        (AuraKind.HYDRO, Element.HYDRO, "incoming_geo_on_hydro"),
        (AuraKind.ELECTRO, Element.ELECTRO, "incoming_geo_on_electro"),
        (AuraKind.CRYO, Element.CRYO, "incoming_geo_on_cryo"),
    ),
)
def test_crystallize_single_aura_directions_declare_one_shard_without_damage_effect(
    aura_kind: AuraKind,
    shard_element: Element,
    direction: str,
) -> None:
    resolution = _evaluate(aura_kind=aura_kind, aura_amount=AuraAmount.one())

    assert resolution.occurrence is not None
    occurrence = resolution.occurrence
    assert occurrence.reaction_key == "reaction.crystallize"
    assert occurrence.direction_key == direction
    assert occurrence.effect_groups == ()
    assert resolution.damage_adjustment is None
    assert occurrence.transition.incoming_consumed == AuraAmount.one()
    assert occurrence.transition.aura_consumed == AuraAmount("1/2")
    assert occurrence.transition.aura_remaining == AuraAmount("1/2")
    assert occurrence.crystallize_shard_state_creation is not None
    assert occurrence.spatial_entity_creation is not None
    shard = occurrence.crystallize_shard_state_creation
    spatial = occurrence.spatial_entity_creation
    assert shard.element is shard_element
    assert shard.instance_ref.value == (
        f"reaction-state:crystallize-shard:{occurrence.occurrence_ref}"
    )
    assert shard.space_entity_ref == (
        f"reaction_object:crystallize_shard:{occurrence.occurrence_ref}"
    )
    assert shard.expires_at_frame == 900
    assert spatial.source_key == shard.instance_ref.value
    assert spatial.space_entity_ref == shard.space_entity_ref
    assert spatial.tags == ("reaction_object", "crystallize_shard")


@pytest.mark.parametrize(
    ("incoming", "aura", "expected_geo_consumed", "expected_aura_consumed"),
    (
        (AuraAmount(1), AuraAmount(1), Fraction(1), Fraction(1, 2)),
        (AuraAmount(2), AuraAmount(1), Fraction(2), Fraction(1)),
        (AuraAmount(3), AuraAmount(1), Fraction(2), Fraction(1)),
    ),
)
def test_crystallize_consumes_geo_and_aura_at_exact_two_to_one_ratio(
    incoming: AuraAmount,
    aura: AuraAmount,
    expected_geo_consumed: Fraction,
    expected_aura_consumed: Fraction,
) -> None:
    resolution = _evaluate(aura_kind=AuraKind.PYRO, aura_amount=aura, incoming_amount=incoming)

    assert resolution.occurrence is not None
    transition = resolution.occurrence.transition
    assert transition.incoming_consumed == AuraAmount(expected_geo_consumed)
    assert transition.aura_consumed == AuraAmount(expected_aura_consumed)
    assert transition.incoming_remaining == incoming - AuraAmount(expected_geo_consumed)
    assert transition.aura_remaining == aura - AuraAmount(expected_aura_consumed)


def test_default_bootstrap_registers_crystallize_with_its_establishment_gate():
    bootstrap = create_default_reaction_bootstrap()
    registry = bootstrap.reaction_registry

    assert "reaction.crystallize" in {
        definition.reaction_key for definition in registry.definitions
    }
    assert bootstrap.establishment_gate_definitions == (
        crystallize_establishment_gate_definition(),
    )


def test_crystallize_does_not_choose_a_multi_aura_or_frozen_candidate_implicitly() -> None:
    runtime = ReactionRuntime(ReactionRegistry((crystallize_definition(),)))
    request = _request(
        AuraView(
            TARGET,
            (
                _component(AuraKind.PYRO, AuraAmount.one()),
                _component(AuraKind.HYDRO, AuraAmount.one()),
            ),
        )
    )

    assert runtime.evaluate(request).occurrence is None

    frozen_request = _request(
        AuraView(
            TARGET,
            (
                _component(AuraKind.FROZEN, AuraAmount.one()),
                _component(AuraKind.PYRO, AuraAmount.one()),
            ),
        )
    )
    assert runtime.evaluate(frozen_request).occurrence is None


def test_crystallize_on_water_electro_blocks_second_candidate_with_same_frame_gate():
    runtime = ReactionRuntime(
        ReactionRegistry((crystallize_definition(),)),
        establishment_gate_definitions=(crystallize_establishment_gate_definition(),),
    )
    planner = runtime.begin_batch(0, "crystallize-water-electro-gate")

    resolution = planner.prepare(
        _request(
            AuraView(
                TARGET,
                (
                    _component(AuraKind.HYDRO, AuraAmount.one()),
                    _component(AuraKind.ELECTRO, AuraAmount.one()),
                ),
            ),
            AuraAmount(3),
        )
    )
    plan = planner.seal()

    occurrences = tuple(
        occurrence for step in resolution.sequence.steps for occurrence in step.occurrences
    )
    assert tuple(occurrence.direction_key for occurrence in occurrences) == (
        "incoming_geo_on_electro",
    )
    assert resolution.establishment_gate_blocked
    assert plan.establishment_gate_plan is not None
    gate_resolutions = plan.establishment_gate_plan.resolutions
    assert tuple(item.decision for item in gate_resolutions) == (
        ReactionEstablishmentGateDecision.ALLOWED,
        ReactionEstablishmentGateDecision.ESTABLISHMENT_GATE_BLOCKED,
    )
    assert len({item.slot_key for item in gate_resolutions}) == 1


def test_crystallize_establishment_gate_uses_the_batch_virtual_projection():
    runtime = ReactionRuntime(
        ReactionRegistry((crystallize_definition(),)),
        establishment_gate_definitions=(crystallize_establishment_gate_definition(),),
    )
    planner = runtime.begin_batch(0, "crystallize-gate-projection")
    first = planner.prepare(
        _request(AuraView(TARGET, (_component(AuraKind.PYRO, AuraAmount.one()),)))
    )
    blocked = planner.prepare(
        replace(
            _request(AuraView(TARGET, (_component(AuraKind.PYRO, AuraAmount.one()),))),
            interaction_id="interaction:crystallize:second",
            order=1,
        )
    )
    plan = planner.seal()

    assert first.occurrence is not None
    assert blocked.occurrence is None
    assert blocked.establishment_gate_blocked
    assert plan.establishment_gate_plan is not None
    assert tuple(
        resolution.decision for resolution in plan.establishment_gate_plan.resolutions
    ) == (
        ReactionEstablishmentGateDecision.ALLOWED,
        ReactionEstablishmentGateDecision.ESTABLISHMENT_GATE_BLOCKED,
    )
    assert len(plan.establishment_gate_plan.replacement_records) == 1


def test_crystallize_after_blunt_shattered_reads_exposed_hidden_hydro_only():
    link = ElementalStateLinkRef("elemental-state-link:frozen")
    frozen = FrozenState(ReactionStateInstanceRef("state:frozen"), TARGET, link, 100)
    runtime = create_default_reaction_bootstrap().create_runtime()

    resolution = runtime.evaluate(
        ReactionEvaluationRequest(
            "interaction:frozen-geo",
            "impact:target",
            0,
            0,
            SOURCE,
            TARGET,
            Element.GEO,
            AuraAmount.one(),
            AuraView(
                TARGET,
                (
                    _component(AuraKind.HYDRO, AuraAmount.one()),
                    _component(AuraKind.FROZEN, AuraAmount.one()),
                ),
            ),
            transformative_source_observation=_transformative_observation(),
            trigger_context=ReactionTriggerContext(
                elemental_application=ReactionElementalApplication(Element.GEO, AuraAmount.one()),
                strike_type=StrikeType.BLUNT,
            ),
            observed_frozen_state=frozen,
            crystallize_source_observation=CrystallizeSourceObservation(SOURCE, 90, 0),
        )
    )

    occurrences = tuple(
        occurrence for step in resolution.sequence.steps for occurrence in step.occurrences
    )
    assert tuple(occurrence.reaction_key for occurrence in occurrences) == (
        "reaction.shattered",
        "reaction.crystallize",
    )
    assert occurrences[1].direction_key == "incoming_geo_on_hydro"


def test_crystallize_does_not_read_hidden_hydro_without_blunt_shattered():
    link = ElementalStateLinkRef("elemental-state-link:frozen")
    frozen = FrozenState(ReactionStateInstanceRef("state:frozen"), TARGET, link, 100)
    runtime = create_default_reaction_bootstrap().create_runtime()

    resolution = runtime.evaluate(
        ReactionEvaluationRequest(
            "interaction:frozen-geo-no-blunt",
            "impact:target",
            0,
            0,
            SOURCE,
            TARGET,
            Element.GEO,
            AuraAmount.one(),
            AuraView(
                TARGET,
                (
                    _component(AuraKind.HYDRO, AuraAmount.one()),
                    _component(AuraKind.FROZEN, AuraAmount.one()),
                ),
            ),
            trigger_context=ReactionTriggerContext(
                elemental_application=ReactionElementalApplication(Element.GEO, AuraAmount.one()),
            ),
            observed_frozen_state=frozen,
            crystallize_source_observation=CrystallizeSourceObservation(SOURCE, 90, 0),
        )
    )

    assert resolution.occurrence is None


def test_crystallize_requires_its_own_source_observation() -> None:
    runtime = ReactionRuntime(ReactionRegistry((crystallize_definition(),)))
    request = _request(AuraView(TARGET, (_component(AuraKind.PYRO, AuraAmount.one()),)))
    request = type(request)(
        request.interaction_id,
        request.target_impact_ref,
        request.frame,
        request.order,
        request.source_ref,
        request.subject_ref,
        request.incoming_element,
        request.incoming_amount,
        request.observed_aura,
    )

    with pytest.raises(ValueError, match="结晶需要已捕获的结晶来源观察"):
        runtime.evaluate(request)


def test_crystallize_level_table_is_exact_and_formula_captures_the_source_once() -> None:
    assert tuple(crystallize_level_coefficient(level) for level in range(1, 101)) == (
        _EXPECTED_LEVEL_COEFFICIENTS
    )
    observation = CrystallizeSourceObservation(SOURCE, 90, 1400)
    basis = capture_crystallize_shield_basis(observation, captured_frame=12)

    assert elemental_mastery_bonus(1400) == pytest.approx(20 / 9)
    assert basis.crystallize_level_coefficient == 1851.060
    assert basis.source_elemental_mastery == 1400
    assert basis.native_absorption == pytest.approx(1851.060 * (1 + 20 / 9))


@pytest.mark.parametrize("level", (0, 101, 1.0, True))
def test_crystallize_level_table_rejects_values_outside_its_direct_range(level: object) -> None:
    with pytest.raises(CrystallizeLevelOutOfRangeError):
        crystallize_level_coefficient(level)  # type: ignore[arg-type]


def _evaluate(
    *,
    aura_kind: AuraKind,
    aura_amount: AuraAmount,
    incoming_amount: AuraAmount | None = None,
):
    runtime = ReactionRuntime(ReactionRegistry((crystallize_definition(),)))
    incoming_amount = AuraAmount.one() if incoming_amount is None else incoming_amount
    return runtime.evaluate(
        _request(AuraView(TARGET, (_component(aura_kind, aura_amount),)), incoming_amount)
    )


def _request(
    view: AuraView,
    incoming_amount: AuraAmount | None = None,
) -> ReactionEvaluationRequest:
    incoming_amount = AuraAmount.one() if incoming_amount is None else incoming_amount
    return ReactionEvaluationRequest(
        "interaction:crystallize",
        "impact:target",
        0,
        0,
        SOURCE,
        TARGET,
        Element.GEO,
        incoming_amount,
        view,
        crystallize_source_observation=CrystallizeSourceObservation(SOURCE, 90, 0),
    )


def _component(aura_kind: AuraKind, amount: AuraAmount) -> AuraComponent:
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
        state_link_refs=(
            (ElementalStateLinkRef(f"elemental-state-link:{aura_kind.value}"),)
            if aura_kind is AuraKind.FROZEN
            else ()
        ),
        decay_mode=(
            AuraDecayMode.STATE_LINKED if aura_kind is AuraKind.FROZEN else AuraDecayMode.STANDARD
        ),
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
