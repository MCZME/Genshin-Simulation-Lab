from __future__ import annotations

from genshin_sim.core.coordination.elemental_reaction.lunar_storm_cloud import (
    plan_lunar_storm_cloud_occurrence,
)
from genshin_sim.core.coordination.elemental_reaction.spatial import (
    ReactionSpatialPlanningAdapter,
)
from genshin_sim.core.elements import ElementalSourceRef, ElementalSubjectRef
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.systems.reaction import (
    ReactionRuntime,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_STORM_CLOUD_SPATIAL_PROFILE_KEY,
    LUNAR_STORM_CLOUD_STATE_KEY,
    LUNAR_STORM_CLOUD_TEAM_SCOPE,
)
from genshin_sim.core.systems.reaction.models import (
    LunarStormCloudStatePlanningIntent,
    SpatialEntityCreationEffect,
)
from genshin_sim.core.systems.reaction.states import ReactionStateInstanceRef

SOURCE = ElementalSourceRef("character:slot_1")
TARGET_1 = ElementalSubjectRef.target("target:target_1")
TARGET_2 = ElementalSubjectRef.target("target:target_2")
TARGET_3 = ElementalSubjectRef.target("target:target_3")


class _FakeSpaceRuntime:
    def __init__(self, space: Space) -> None:
        self.space = space

    def get_entity(self, entity_id: str) -> SpatialEntity | None:
        return self.space.get_entity(entity_id)


class _FakeContext:
    def __init__(self, space_runtime: _FakeSpaceRuntime) -> None:
        self.space_runtime = space_runtime


def _target_entity(subject_ref: ElementalSubjectRef, position: Vector3) -> SpatialEntity:
    return SpatialEntity(
        entity_id=subject_ref.entity_id,
        kind=SpatialEntityKind.TARGET,
        position=position,
    )


def _intent(
    occurrence_ref: str,
    subject_ref: ElementalSubjectRef,
    *,
    frame: int = 0,
) -> LunarStormCloudStatePlanningIntent:
    instance_ref = ReactionStateInstanceRef(f"reaction-state:lunar-storm-cloud:{occurrence_ref}")
    return LunarStormCloudStatePlanningIntent(
        intent_ref=f"{occurrence_ref}:plan",
        parent_occurrence_ref=occurrence_ref,
        instance_ref=instance_ref,
        subject_ref=subject_ref,
        space_entity_ref=f"reaction_object:lunar_storm_cloud:{occurrence_ref}",
        trigger_source_ref=SOURCE,
        team_ref=LUNAR_STORM_CLOUD_TEAM_SCOPE,
        created_frame=frame,
        expires_at_frame=frame + 360,
        first_attack_frame=frame + 15,
        attack_interval_frames=15,
    )


def _spatial_effect(intent: LunarStormCloudStatePlanningIntent) -> SpatialEntityCreationEffect:
    return SpatialEntityCreationEffect(
        effect_ref=f"{intent.parent_occurrence_ref}:spatial",
        parent_occurrence_ref=intent.parent_occurrence_ref,
        space_entity_ref=intent.space_entity_ref,
        owner_key=LUNAR_STORM_CLOUD_TEAM_SCOPE,
        source_key=intent.instance_ref.value,
        tags=(LUNAR_STORM_CLOUD_STATE_KEY, LUNAR_STORM_CLOUD_SPATIAL_PROFILE_KEY),
        created_frame=intent.created_frame,
        expires_at_frame=intent.expires_at_frame,
    )


def _fixtures() -> tuple[ReactionRuntime, Space, _FakeContext]:
    runtime = create_default_reaction_bootstrap().create_runtime()
    runtime.update_frame(None, 0)
    space = Space(
        (
            _target_entity(TARGET_1, Vector3(0.0, 0.0, 0.0)),
            _target_entity(TARGET_2, Vector3(10.0, 0.0, 0.0)),
            _target_entity(TARGET_3, Vector3(5.0, 0.0, 0.0)),
        )
    )
    context = _FakeContext(_FakeSpaceRuntime(space))
    return runtime, space, context


def test_plan_creates_cloud_when_none_nearby_and_refreshes_existing() -> None:
    runtime, space, context = _fixtures()
    state_planner = runtime.begin_state_batch(0, "cloud:plan:0")
    spatial_planner = ReactionSpatialPlanningAdapter(space).begin_batch(
        operation_id="cloud:plan:0",
        frame=0,
    )

    first = _intent("occurrence:1", TARGET_1)
    result = plan_lunar_storm_cloud_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=first,
        spatial_effect=_spatial_effect(first),
    )
    assert result.created
    assert not result.refreshed
    cloud = state_planner.lunar_storm_cloud_for(first.instance_ref)
    assert cloud is not None
    assert cloud.next_attack_frame == 15
    assert cloud.expires_at_frame == 360

    second = _intent("occurrence:2", TARGET_1, frame=10)
    result = plan_lunar_storm_cloud_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=second,
        spatial_effect=_spatial_effect(second),
    )
    assert not result.created
    assert result.refreshed
    refreshed = state_planner.lunar_storm_cloud_for(first.instance_ref)
    assert refreshed is not None
    assert refreshed.expires_at_frame == 370
    assert refreshed.revision == 2
    assert refreshed.next_attack_frame == 15
    assert len(state_planner.active_lunar_storm_clouds()) == 1
    assert len(spatial_planner.creation_receipts) == 1


def test_plan_keeps_one_cloud_and_destroys_extra_when_too_close() -> None:
    runtime, space, context = _fixtures()
    state_planner = runtime.begin_state_batch(0, "cloud:plan:1")
    spatial_planner = ReactionSpatialPlanningAdapter(space).begin_batch(
        operation_id="cloud:plan:1",
        frame=0,
    )

    first = _intent("occurrence:a", TARGET_1)
    plan_lunar_storm_cloud_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=first,
        spatial_effect=_spatial_effect(first),
    )
    second = _intent("occurrence:b", TARGET_2)
    plan_lunar_storm_cloud_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=second,
        spatial_effect=_spatial_effect(second),
    )
    assert len(state_planner.active_lunar_storm_clouds()) == 2

    third = _intent("occurrence:c", TARGET_3, frame=5)
    result = plan_lunar_storm_cloud_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=third,
        spatial_effect=_spatial_effect(third),
    )
    assert result.refreshed
    assert result.removed_extra == (second.instance_ref,)
    remaining = state_planner.active_lunar_storm_clouds()
    assert [item.instance_ref for item in remaining] == [first.instance_ref]
    assert state_planner.lunar_storm_cloud_for(first.instance_ref) is not None
    assert state_planner.lunar_storm_cloud_for(second.instance_ref) is None
    assert len(spatial_planner.creation_receipts) == 1
    space_plan = spatial_planner.seal()
    assert len(space_plan.creations) == 1
    assert space_plan.removals == ()
