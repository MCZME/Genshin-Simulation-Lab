from __future__ import annotations

from genshin_sim.core.entity_states import EntityLifecycleState
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.space import (
    CreatedObjectRuntime,
    CreatedObjectRuntimeState,
    CreatedObjectSpec,
    CreatedObjectTickSpec,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)


class RecordingCreatedObjectBehavior:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def create_tick_requests(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
    ) -> tuple[ImpactRequest, ...]:
        self.calls.append((state.entity.entity_id, frame))
        return (
            ImpactRequest(
                frame=frame,
                kind=ImpactKind.DAMAGE,
                impact_key=f"{state.object_key}.tick",
                tags=state.entity.tags,
                params=state.params,
            ),
        )


def test_created_object_runtime_creates_and_refreshes_object():
    runtime = CreatedObjectRuntime()
    spec = CreatedObjectSpec(
        object_key="furina.salon_member",
        duration_frames=5,
        owner_key="slot:1",
        entity_id="created:salon_1",
        tags=("created_object",),
    )

    first = runtime.create_or_refresh(spec, frame=10)
    refreshed = runtime.create_or_refresh(spec, frame=12)

    assert refreshed is first
    assert first.entity.kind is SpatialEntityKind.CREATED_OBJECT
    assert first.entity.entity_id == "created:salon_1"
    assert first.entity.owner_key == "slot:1"
    assert first.entity.lifecycle.created_frame == 10
    assert first.entity.lifecycle.expires_at_frame == 17
    assert runtime.objects == (first,)
    assert runtime.active_objects == (first,)


def test_created_object_runtime_respects_max_instances_before_refreshing_oldest():
    runtime = CreatedObjectRuntime()
    spec = CreatedObjectSpec(
        object_key="created.multi",
        duration_frames=10,
        max_instances=2,
        refresh_existing=False,
    )

    first = runtime.create_or_refresh(spec, frame=1)
    second = runtime.create_or_refresh(spec, frame=2)
    capped = runtime.create_or_refresh(spec, frame=3)

    assert capped is first
    assert runtime.objects == (first, second)
    assert first.entity.lifecycle.expires_at_frame == 13
    assert second.entity.lifecycle.expires_at_frame == 12


def test_created_object_runtime_tick_emits_impact_requests():
    ctx = SimulationContext()
    behavior = RecordingCreatedObjectBehavior()
    runtime = CreatedObjectRuntime({"furina.salon_member": behavior})
    spec = CreatedObjectSpec(
        object_key="furina.salon_member",
        duration_frames=6,
        first_tick_frame_offset=1,
        tick_interval_frames=2,
        tags=("created_object",),
        params={"member": "chevalmarin"},
    )

    obj = runtime.create_or_refresh(spec, frame=1)
    runtime.update_frame(ctx, 2)

    assert behavior.calls == [(obj.entity.entity_id, 2)]
    assert [
        (request.frame, request.kind, request.impact_key, request.tags, request.params)
        for request in runtime.pending_impact_requests
    ] == [
        (
            2,
            ImpactKind.DAMAGE,
            "furina.salon_member.tick",
            ("created_object",),
            {"member": "chevalmarin"},
        )
    ]

    runtime.update_frame(ctx, 3)
    assert runtime.pending_impact_requests == ()

    runtime.update_frame(ctx, 4)
    assert len(runtime.emitted_impact_requests) == 2


def test_created_object_runtime_expires_at_end_frame_and_becomes_idle():
    ctx = SimulationContext()
    behavior = RecordingCreatedObjectBehavior()
    runtime = CreatedObjectRuntime({"created.short": behavior})
    spec = CreatedObjectSpec(
        object_key="created.short",
        duration_frames=2,
        first_tick_frame_offset=2,
    )

    obj = runtime.create_or_refresh(spec, frame=1)
    runtime.update_frame(ctx, 3)

    assert obj.entity.lifecycle.state is EntityLifecycleState.EXPIRED
    assert runtime.active_objects == ()
    assert runtime.pending_impact_requests == ()
    assert behavior.calls == []
    assert runtime.is_idle()


def test_created_object_expiration_replaces_the_immutable_spatial_entity():
    ctx = SimulationContext()
    runtime = CreatedObjectRuntime()
    obj = runtime.create_or_refresh(
        CreatedObjectSpec(object_key="created.short", duration_frames=1),
        frame=1,
    )
    entity_before_expiry = obj.entity

    runtime.update_frame(ctx, 2)

    assert entity_before_expiry.lifecycle.state is EntityLifecycleState.ACTIVE
    assert obj.entity.lifecycle.state is EntityLifecycleState.EXPIRED
    assert obj.entity is not entity_before_expiry


def test_created_object_runtime_supports_multiple_tick_schedules():
    ctx = SimulationContext()
    heal_behavior = RecordingCreatedObjectBehavior()
    wet_behavior = RecordingCreatedObjectBehavior()
    runtime = CreatedObjectRuntime(
        {
            "barbara.ring.heal": heal_behavior,
            "barbara.ring.wet": wet_behavior,
        }
    )
    spec = CreatedObjectSpec(
        object_key="barbara.ring",
        duration_frames=300,
        tick_schedules=(
            CreatedObjectTickSpec(
                "barbara.ring.heal",
                first_tick_frame_offset=6,
                interval_frames=300,
            ),
            CreatedObjectTickSpec(
                "barbara.ring.wet",
                first_tick_frame_offset=36,
                interval_frames=90,
            ),
        ),
    )

    obj = runtime.create_or_refresh(spec, frame=100)
    runtime.update_frame(ctx, 106)

    assert heal_behavior.calls == [(obj.entity.entity_id, 106)]
    assert wet_behavior.calls == []

    runtime.update_frame(ctx, 136)
    assert wet_behavior.calls == [(obj.entity.entity_id, 136)]

    runtime.update_frame(ctx, 196)
    assert wet_behavior.calls == [(obj.entity.entity_id, 136)]

    runtime.update_frame(ctx, 226)
    assert wet_behavior.calls == [
        (obj.entity.entity_id, 136),
        (obj.entity.entity_id, 226),
    ]


class _FakeSpaceRuntime:
    def __init__(self, entity: SpatialEntity) -> None:
        self._entity = entity

    def get_entity(self, entity_id: str) -> SpatialEntity | None:
        if entity_id == self._entity.entity_id:
            return self._entity
        return None


def test_created_object_runtime_syncs_following_entity_position():
    follower = SpatialEntity(
        entity_id="player:active",
        kind=SpatialEntityKind.ACTIVE_CHARACTER,
        position=Vector3(5.0, 2.0, 7.0),
    )
    ctx = SimulationContext()
    ctx.space_runtime = _FakeSpaceRuntime(follower)  # type: ignore[assignment]
    runtime = CreatedObjectRuntime()
    spec = CreatedObjectSpec(
        object_key="created.follower",
        duration_frames=10,
        follow_entity_id="player:active",
    )

    obj = runtime.create_or_refresh(spec, frame=1)
    runtime.update_frame(ctx, 2)

    assert obj.entity.position == Vector3(5.0, 2.0, 7.0)


def test_created_object_runtime_extends_duration_with_cap():
    runtime = CreatedObjectRuntime()
    spec = CreatedObjectSpec(
        object_key="barbara.ring",
        duration_frames=100,
        owner_key="slot:1",
    )

    obj = runtime.create_or_refresh(spec, frame=1)
    first = runtime.extend_duration(
        object_key="barbara.ring",
        owner_key="slot:1",
        frames=60,
        max_extra_frames=300,
        frame=10,
    )
    second = runtime.extend_duration(
        object_key="barbara.ring",
        owner_key="slot:1",
        frames=300,
        max_extra_frames=300,
        frame=20,
    )
    capped = runtime.extend_duration(
        object_key="barbara.ring",
        owner_key="slot:1",
        frames=60,
        max_extra_frames=300,
        frame=30,
    )

    assert first is not None
    assert first.applied_frames == 60
    assert first.remaining_cap_frames == 240
    assert second is not None
    assert second.applied_frames == 240
    assert second.remaining_cap_frames == 0
    assert capped is not None
    assert capped.applied_frames == 0
    assert capped.remaining_cap_frames == 0
    assert obj.extra_duration_frames == 300
    assert obj.entity.lifecycle.expires_at_frame == 401
    assert len(runtime.extension_records) == 3


def test_created_object_runtime_refresh_resets_extension_budget():
    runtime = CreatedObjectRuntime()
    spec = CreatedObjectSpec(
        object_key="barbara.ring",
        duration_frames=100,
        owner_key="slot:1",
    )

    obj = runtime.create_or_refresh(spec, frame=1)
    runtime.extend_duration(
        object_key="barbara.ring",
        owner_key="slot:1",
        frames=120,
        max_extra_frames=300,
        frame=10,
    )
    assert obj.extra_duration_frames == 120

    refreshed = runtime.create_or_refresh(spec, frame=50)

    assert refreshed is obj
    assert obj.extra_duration_frames == 0
    assert obj.entity.lifecycle.expires_at_frame == 150
    after = runtime.extend_duration(
        object_key="barbara.ring",
        owner_key="slot:1",
        frames=60,
        max_extra_frames=300,
        frame=60,
    )
    assert after is not None
    assert after.applied_frames == 60
    assert obj.entity.lifecycle.expires_at_frame == 210


def test_created_object_runtime_extension_ignores_missing_or_expired_object():
    runtime = CreatedObjectRuntime()
    spec = CreatedObjectSpec(
        object_key="barbara.ring",
        duration_frames=10,
        owner_key="slot:1",
    )

    runtime.create_or_refresh(spec, frame=1)
    wrong_owner = runtime.extend_duration(
        object_key="barbara.ring",
        owner_key="slot:2",
        frames=60,
        max_extra_frames=300,
        frame=2,
    )
    unknown = runtime.extend_duration(
        object_key="other.object",
        owner_key="slot:1",
        frames=60,
        max_extra_frames=300,
        frame=2,
    )
    expired = runtime.extend_duration(
        object_key="barbara.ring",
        owner_key="slot:1",
        frames=60,
        max_extra_frames=300,
        frame=12,
    )

    assert wrong_owner is None
    assert unknown is None
    assert expired is None
    assert runtime.extension_records == ()
