from __future__ import annotations

from genshin_sim.core.entity_states import EntityLifecycleState
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.space import (
    CreatedObjectRuntime,
    CreatedObjectRuntimeState,
    CreatedObjectSpec,
    SpatialEntityKind,
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
