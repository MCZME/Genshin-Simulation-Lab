# 单一关注点：创建物运行时的生命周期与 tick 驱动。
# 覆盖：创建与刷新重建运行态、实例上限后刷新最旧、tick 产出影响请求并携带
# 仿真上下文、过期帧与 idle 判定、过期替换不可变空间实体、多调度并行推进、
# 跟随实体位置同步、类型未推进调度的确定性报错。
from __future__ import annotations

import pytest

from genshin_sim.core.entity_states import EntityLifecycleState
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.space import (
    CreatedObjectRuntime,
    CreatedObjectRuntimeState,
    CreatedObjectSpec,
    CreatedObjectTickState,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from tests.helpers.space import RecordingCreatedEntityType


def test_created_object_runtime_creates_and_refreshes_object():
    type_impl = RecordingCreatedEntityType("furina.salon_member")
    runtime = CreatedObjectRuntime({"furina.salon_member": type_impl})
    spec = CreatedObjectSpec(
        type_key="furina.salon_member",
        duration_frames=5,
        owner_key="slot:1",
        entity_id="created:salon_1",
        tags=("created_object",),
    )

    first = runtime.create_or_refresh(spec, frame=10)
    refreshed = runtime.create_or_refresh(spec, frame=12)

    # 刷新重建运行态（类型接管），但实体身份与创建帧保留。
    assert refreshed is not first
    assert refreshed.entity.entity_id == "created:salon_1"
    assert refreshed.entity.kind is SpatialEntityKind.CREATED_OBJECT
    assert refreshed.entity.owner_key == "slot:1"
    assert refreshed.entity.lifecycle.created_frame == 10
    assert refreshed.entity.lifecycle.expires_at_frame == 17
    assert runtime.objects == (refreshed,)
    assert runtime.active_objects == (refreshed,)


def test_created_object_runtime_respects_max_instances_before_refreshing_oldest():
    type_impl = RecordingCreatedEntityType("created.multi")
    runtime = CreatedObjectRuntime({"created.multi": type_impl})
    spec = CreatedObjectSpec(
        type_key="created.multi",
        duration_frames=10,
        max_instances=2,
        refresh_existing=False,
    )

    first = runtime.create_or_refresh(spec, frame=1)
    second = runtime.create_or_refresh(spec, frame=2)
    capped = runtime.create_or_refresh(spec, frame=3)

    assert capped is not first
    assert capped.entity.entity_id == first.entity.entity_id
    assert runtime.objects == (capped, second)
    assert capped.entity.lifecycle.expires_at_frame == 13
    assert second.entity.lifecycle.expires_at_frame == 12


def test_created_object_runtime_tick_emits_impact_requests():
    ctx = SimulationContext()
    type_impl = RecordingCreatedEntityType(
        "furina.salon_member",
        schedule_seeds=(("tick", 1, 2),),
    )
    runtime = CreatedObjectRuntime({"furina.salon_member": type_impl})
    spec = CreatedObjectSpec(
        type_key="furina.salon_member",
        duration_frames=6,
        tags=("created_object",),
    )

    obj = runtime.create_or_refresh(spec, frame=1)
    runtime.update_frame(ctx, 2)

    assert type_impl.calls == [(obj.entity.entity_id, 2, "tick")]
    # 类型 on_tick 按协议收到仿真上下文（星变体分派等现场查询依赖）。
    assert type_impl.contexts == [ctx]
    assert [
        (request.frame, request.kind, request.impact_key, request.tags)
        for request in runtime.pending_impact_requests
    ] == [
        (
            2,
            ImpactKind.DAMAGE,
            "furina.salon_member.tick",
            ("created_object",),
        )
    ]

    runtime.update_frame(ctx, 3)
    assert runtime.pending_impact_requests == ()

    runtime.update_frame(ctx, 4)
    assert len(runtime.emitted_impact_requests) == 2


def test_created_object_runtime_expires_at_end_frame_and_becomes_idle():
    ctx = SimulationContext()
    type_impl = RecordingCreatedEntityType(
        "created.short",
        schedule_seeds=(("tick", 2, None),),
    )
    runtime = CreatedObjectRuntime({"created.short": type_impl})
    spec = CreatedObjectSpec(type_key="created.short", duration_frames=2)

    obj = runtime.create_or_refresh(spec, frame=1)
    runtime.update_frame(ctx, 3)

    assert obj.entity.lifecycle.state is EntityLifecycleState.EXPIRED
    assert runtime.active_objects == ()
    assert runtime.pending_impact_requests == ()
    assert type_impl.calls == []
    assert runtime.is_idle()


def test_created_object_expiration_replaces_the_immutable_spatial_entity():
    ctx = SimulationContext()
    type_impl = RecordingCreatedEntityType("created.short")
    runtime = CreatedObjectRuntime({"created.short": type_impl})
    obj = runtime.create_or_refresh(
        CreatedObjectSpec(type_key="created.short", duration_frames=1),
        frame=1,
    )
    entity_before_expiry = obj.entity

    runtime.update_frame(ctx, 2)

    assert entity_before_expiry.lifecycle.state is EntityLifecycleState.ACTIVE
    assert obj.entity.lifecycle.state is EntityLifecycleState.EXPIRED
    assert obj.entity is not entity_before_expiry


def test_created_object_runtime_supports_multiple_tick_schedules():
    ctx = SimulationContext()
    type_impl = RecordingCreatedEntityType(
        "barbara.ring",
        schedule_seeds=(
            ("heal", 6, 300),
            ("wet", 36, 90),
        ),
    )
    runtime = CreatedObjectRuntime({"barbara.ring": type_impl})
    spec = CreatedObjectSpec(type_key="barbara.ring", duration_frames=300)

    obj = runtime.create_or_refresh(spec, frame=100)
    runtime.update_frame(ctx, 106)

    assert type_impl.calls == [(obj.entity.entity_id, 106, "heal")]

    runtime.update_frame(ctx, 136)
    assert type_impl.calls == [
        (obj.entity.entity_id, 106, "heal"),
        (obj.entity.entity_id, 136, "wet"),
    ]

    runtime.update_frame(ctx, 196)
    assert type_impl.calls == [
        (obj.entity.entity_id, 106, "heal"),
        (obj.entity.entity_id, 136, "wet"),
    ]

    runtime.update_frame(ctx, 226)
    assert type_impl.calls == [
        (obj.entity.entity_id, 106, "heal"),
        (obj.entity.entity_id, 136, "wet"),
        (obj.entity.entity_id, 226, "wet"),
    ]


def test_created_object_runtime_raises_when_type_does_not_advance_schedule():
    # 推进由类型决定：on_tick 后调度未前进到更晚帧属节奏逻辑缺陷，确定性报错
    # 而非静默停摆；显式置 None（一次性）是合法停机。
    ctx = SimulationContext()

    class _StallingType(RecordingCreatedEntityType):
        def on_tick(
            self,
            state: CreatedObjectRuntimeState,
            schedule: CreatedObjectTickState,
            frame: int,
            context: SimulationContext,
        ) -> tuple[ImpactRequest, ...]:
            del schedule, context  # 故意不推进
            return ()

    type_impl = _StallingType(
        "created.stall",
        schedule_seeds=(("tick", 1, None),),
    )
    runtime = CreatedObjectRuntime({"created.stall": type_impl})
    runtime.create_or_refresh(
        CreatedObjectSpec(type_key="created.stall", duration_frames=100),
        frame=1,
    )

    with pytest.raises(ValueError, match="未推进到更晚帧"):
        runtime.update_frame(ctx, 2)


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
    type_impl = RecordingCreatedEntityType("created.follower")
    runtime = CreatedObjectRuntime({"created.follower": type_impl})
    spec = CreatedObjectSpec(
        type_key="created.follower",
        duration_frames=10,
        follow_entity_id="player:active",
    )

    obj = runtime.create_or_refresh(spec, frame=1)
    runtime.update_frame(ctx, 2)

    assert obj.follow_entity_id == "player:active"
    assert obj.entity.position == Vector3(5.0, 2.0, 7.0)
