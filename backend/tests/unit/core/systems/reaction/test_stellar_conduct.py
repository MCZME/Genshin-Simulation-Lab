import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraRuntime, AuraStrength
from genshin_sim.core.systems.reaction import (
    PolestarFieldStatePlanningIntent,
    ReactionEvaluationRequest,
    ReactionStateInstanceRef,
    StellarConductAttachmentRecord,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct import (
    STELLAR_CONDUCT_CAPABILITY_KEY,
    STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES,
    STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
    STELLAR_CONDUCT_REACTION_KEY,
    STELLAR_CONDUCT_TEAM_SCOPE,
    PolestarFieldState,
    StellarConductCounterState,
    stellar_conduct_definition,
    stellar_conduct_direct_multiplier,
    stellar_conduct_elemental_bonus,
)
from genshin_sim.core.systems.reaction.models import (
    StateReactionProfile,
    TransformativeSourceObservation,
)

SOURCE = ElementalSourceRef("character:slot_1")
CHARACTER_SOURCES = (SOURCE,)
TARGET = ElementalSubjectRef.target("target:star")


@pytest.mark.parametrize(
    ("stacks", "expected"),
    [(0, 1.0), (1, 1.45), (12, 2.0), (13, 2.0)],
)
def test_stellar_conduct_direct_multiplier(stacks: int, expected: float) -> None:
    assert stellar_conduct_direct_multiplier(stacks) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("stacks", "expected"),
    [(0, 0.20), (1, 0.29), (12, 0.40), (13, 0.40)],
)
def test_stellar_conduct_elemental_bonus(stacks: int, expected: float) -> None:
    assert stellar_conduct_elemental_bonus(stacks) == pytest.approx(expected)


@pytest.mark.parametrize("stacks", [-1, "1", 1.5, True])
def test_stellar_conduct_coefficients_reject_invalid_stacks(stacks: object) -> None:
    with pytest.raises(ValueError, match="stacks"):
        stellar_conduct_direct_multiplier(stacks)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="stacks"):
        stellar_conduct_elemental_bonus(stacks)  # type: ignore[arg-type]


def _apply_electro_aura() -> AuraRuntime:
    runtime = AuraRuntime()
    runtime.apply(
        AuraApplicationRequest(
            "aura:electro",
            "aura:electro:application",
            "impact:aura:electro",
            0,
            0,
            SOURCE,
            TARGET,
            Element.ELECTRO,
            AuraStrength.WEAK,
        )
    )
    return runtime


def _observation() -> TransformativeSourceObservation:
    return TransformativeSourceObservation(
        source_ref=SOURCE,
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        elemental_mastery=0.0,
        level_multiplier_table_key="transformative.level_multipliers",
        level_multiplier=1.0,
        source_observation_ref="obs:character:slot_1",
        source_owner_slot=1,
    )


def _request(
    aura_runtime: AuraRuntime,
    *,
    incoming: Element = Element.CRYO,
    capability: bool = True,
) -> ReactionEvaluationRequest:
    return ReactionEvaluationRequest(
        "interaction:stellar-conduct",
        "impact:stellar-conduct",
        7,
        0,
        SOURCE,
        TARGET,
        incoming,
        AuraAmount.one(),
        aura_runtime.view(TARGET),
        transformative_source_observation=_observation(),
        character_source_refs=CHARACTER_SOURCES,
        reaction_capability_keys=(
            frozenset({STELLAR_CONDUCT_CAPABILITY_KEY}) if capability else frozenset()
        ),
    )


def test_stellar_conduct_rule_declares_field_plan_without_reaction_damage() -> None:
    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(_request(_apply_electro_aura()))
    )

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == STELLAR_CONDUCT_REACTION_KEY
    assert result.occurrence.effect_groups == ()
    intent = result.occurrence.polestar_field_state_planning
    assert intent is not None
    assert intent.team_ref == STELLAR_CONDUCT_TEAM_SCOPE
    assert intent.created_frame == 7
    assert intent.expires_at_frame == 7 + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES
    assert intent.excluded_attack_ref == "impact:stellar-conduct"
    transition = result.occurrence.transition
    assert transition.aura_consumed == transition.incoming_consumed


def test_stellar_conduct_falls_back_to_superconduct_without_capability() -> None:
    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(_request(_apply_electro_aura(), capability=False))
    )

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == "reaction.superconduct"
    assert result.occurrence.polestar_field_state_planning is None
    assert result.occurrence.effect_groups


def test_stellar_conduct_definition_uses_state_profiles() -> None:
    definition = stellar_conduct_definition()
    for signature in definition.trigger_signatures:
        profile = definition.profile_for(signature.direction_key)
        assert isinstance(profile, StateReactionProfile)


def _field_intent(occurrence_ref: str, *, frame: int = 0) -> PolestarFieldStatePlanningIntent:
    return PolestarFieldStatePlanningIntent(
        intent_ref=f"{occurrence_ref}:polestar-field-plan",
        parent_occurrence_ref=occurrence_ref,
        instance_ref=ReactionStateInstanceRef(f"reaction-state:polestar-field:{occurrence_ref}"),
        subject_ref=TARGET,
        space_entity_ref=f"reaction_object:polestar_field:{occurrence_ref}",
        trigger_source_ref=SOURCE,
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        created_frame=frame,
        expires_at_frame=frame + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
        excluded_attack_ref=f"impact:{occurrence_ref}",
    )


def _record(record_ref: str, *, frame: int = 1) -> StellarConductAttachmentRecord:
    return StellarConductAttachmentRecord(
        record_ref=record_ref,
        attack_ref="impact:attack",
        element=Element.CRYO,
        frame=frame,
        target_refs=(TARGET,),
    )


def test_polestar_field_state_requires_deterministic_identity() -> None:
    intent = _field_intent("occurrence:1")
    state = PolestarFieldState(
        instance_ref=intent.instance_ref,
        space_entity_ref=intent.space_entity_ref,
        subject_ref=intent.subject_ref,
        created_by_occurrence_ref=intent.parent_occurrence_ref,
        trigger_source_ref=intent.trigger_source_ref,
        team_ref=intent.team_ref,
        created_frame=intent.created_frame,
        expires_at_frame=intent.expires_at_frame,
    )
    assert state.next_required_frame == STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES

    with pytest.raises(ValueError, match="instance_ref"):
        PolestarFieldState(
            instance_ref=ReactionStateInstanceRef("reaction-state:polestar-field:other"),
            space_entity_ref=intent.space_entity_ref,
            subject_ref=intent.subject_ref,
            created_by_occurrence_ref=intent.parent_occurrence_ref,
            trigger_source_ref=intent.trigger_source_ref,
            team_ref=intent.team_ref,
            created_frame=0,
            expires_at_frame=STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
        )
    with pytest.raises(ValueError, match="生命周期"):
        PolestarFieldState(
            instance_ref=intent.instance_ref,
            space_entity_ref=intent.space_entity_ref,
            subject_ref=intent.subject_ref,
            created_by_occurrence_ref=intent.parent_occurrence_ref,
            trigger_source_ref=intent.trigger_source_ref,
            team_ref=intent.team_ref,
            created_frame=10,
            expires_at_frame=10 + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES - 1,
        )


def test_attachment_record_restricts_elements() -> None:
    with pytest.raises(ValueError, match="冰或雷"):
        StellarConductAttachmentRecord(
            record_ref="record:1",
            attack_ref="impact:attack",
            element=Element.PYRO,
            frame=1,
            target_refs=(TARGET,),
        )


def test_planner_creates_refreshes_and_removes_polestar_field() -> None:
    runtime = create_default_reaction_bootstrap().create_runtime()
    runtime.update_frame(None, 0)
    planner = runtime.begin_state_batch(0, "polestar:plan:0")

    intent = _field_intent("occurrence:1")
    state = planner.create_polestar_field(intent)
    assert planner.active_polestar_fields(team_ref=STELLAR_CONDUCT_TEAM_SCOPE) == (state,)

    refreshed = planner.replace_polestar_field(
        instance_ref=state.instance_ref,
        expires_at_frame=500 + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
    )
    assert refreshed.instance_ref == state.instance_ref
    assert refreshed.created_frame == 0
    assert refreshed.revision == 2

    with pytest.raises(ValueError, match="缩短"):
        planner.replace_polestar_field(
            instance_ref=state.instance_ref,
            expires_at_frame=100,
        )

    removed = planner.remove_polestar_field(instance_ref=state.instance_ref)
    assert removed.instance_ref == state.instance_ref
    assert planner.active_polestar_fields() == ()


def test_planner_counter_lifecycle_and_window_settlement() -> None:
    runtime = create_default_reaction_bootstrap().create_runtime()
    runtime.update_frame(None, 0)
    planner = runtime.begin_state_batch(0, "counter:plan:0")

    counter = planner.create_stellar_conduct_counter(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        subject_ref=TARGET,
        frame=0,
        excluded_attack_refs=("impact:trigger",),
    )
    assert counter.instance_ref.value == (
        f"reaction-state:stellar-conduct-counter:{STELLAR_CONDUCT_TEAM_SCOPE}"
    )
    assert counter.next_settlement_frame == STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES
    assert counter.excluded_attack_refs == ("impact:trigger",)

    planner.append_stellar_conduct_attachment_record(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:1"),
    )
    planner.append_stellar_conduct_attachment_record(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:2", frame=2),
    )
    with pytest.raises(ValueError, match="不能重复计数"):
        planner.append_stellar_conduct_attachment_record(
            team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
            record=_record("record:1"),
        )

    planner.replace_stellar_conduct_counter_exclusions(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        excluded_attack_refs=("impact:trigger-2",),
    )
    after_exclusions = planner.stellar_conduct_counter_for(STELLAR_CONDUCT_TEAM_SCOPE)
    assert after_exclusions is not None
    assert after_exclusions.excluded_attack_refs == ("impact:trigger-2",)

    settled = planner.settle_stellar_conduct_counter(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        frame=STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES,
    )
    assert settled.settled_stacks == 2
    assert settled.pending_count == 0
    assert settled.recorded_record_refs == ()
    assert settled.excluded_attack_refs == ()
    assert settled.window_index == 2
    assert settled.next_settlement_frame == 2 * STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES
    assert settled.stacks == 2

    with pytest.raises(ValueError, match="next_settlement_frame"):
        planner.settle_stellar_conduct_counter(
            team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
            frame=STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES + 1,
        )

    removed = planner.remove_stellar_conduct_counter(team_ref=STELLAR_CONDUCT_TEAM_SCOPE)
    assert removed.team_ref == STELLAR_CONDUCT_TEAM_SCOPE
    assert planner.stellar_conduct_counter_for(STELLAR_CONDUCT_TEAM_SCOPE) is None


def test_counter_stacks_cap_at_twelve() -> None:
    counter = StellarConductCounterState(
        instance_ref=ReactionStateInstanceRef(
            f"reaction-state:stellar-conduct-counter:{STELLAR_CONDUCT_TEAM_SCOPE}"
        ),
        subject_ref=TARGET,
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        window_start_frame=0,
        next_settlement_frame=STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES,
        settled_stacks=30,
    )
    assert counter.stacks == 12
