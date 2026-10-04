from __future__ import annotations

from collections.abc import Mapping, Sequence

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


class RecordingCreatedEntityType:
    """测试用创建实体类型：按构造给定的调度种子建态，记录每次 on_tick。

    ``schedule_seeds`` 为 (schedule_key, 首拍偏移, 周期|None) 元组：构建时以
    创建帧换算为绝对 ``next_tick_frame``；on_tick 以原定帧 + 周期自行推进，
    周期为 ``None`` 表示一次性（tick 后停机）。
    """

    def __init__(
        self,
        type_key: str,
        schedule_seeds: Sequence[tuple[str, int, int | None]] = (),
    ) -> None:
        self.type_key = type_key
        self._schedule_seeds = tuple(schedule_seeds)
        self.calls: list[tuple[str, int, str]] = []
        self.contexts: list[SimulationContext] = []

    def build_state(
        self,
        config: Mapping[str, object],
        entity: SpatialEntity,
        frame: int,
        previous: CreatedObjectRuntimeState | None,
    ) -> CreatedObjectRuntimeState:
        del config, previous
        return CreatedObjectRuntimeState(
            entity=entity,
            type_key=self.type_key,
            schedules=tuple(
                CreatedObjectTickState(schedule_key=key, next_tick_frame=frame + offset)
                for key, offset, _interval in self._schedule_seeds
            ),
        )

    def on_tick(
        self,
        state: CreatedObjectRuntimeState,
        schedule: CreatedObjectTickState,
        frame: int,
        context: SimulationContext,
    ) -> tuple[ImpactRequest, ...]:
        self.calls.append((state.entity.entity_id, frame, schedule.schedule_key))
        self.contexts.append(context)
        period = next(p for k, _o, p in self._schedule_seeds if k == schedule.schedule_key)
        schedule.next_tick_frame = None if period is None else frame + period
        return (
            ImpactRequest(
                frame=frame,
                kind=ImpactKind.DAMAGE,
                impact_key=f"{state.type_key}.tick",
                tags=state.entity.tags,
            ),
        )


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


def test_created_object_runtime_extends_duration_with_cap():
    type_impl = RecordingCreatedEntityType("barbara.ring")
    runtime = CreatedObjectRuntime({"barbara.ring": type_impl})
    spec = CreatedObjectSpec(type_key="barbara.ring", duration_frames=100, owner_key="slot:1")

    obj = runtime.create_or_refresh(spec, frame=1)
    first = runtime.extend_duration(
        type_key="barbara.ring",
        owner_key="slot:1",
        frames=60,
        max_extra_frames=300,
        frame=10,
    )
    second = runtime.extend_duration(
        type_key="barbara.ring",
        owner_key="slot:1",
        frames=300,
        max_extra_frames=300,
        frame=20,
    )
    capped = runtime.extend_duration(
        type_key="barbara.ring",
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
    type_impl = RecordingCreatedEntityType("barbara.ring")
    runtime = CreatedObjectRuntime({"barbara.ring": type_impl})
    spec = CreatedObjectSpec(type_key="barbara.ring", duration_frames=100, owner_key="slot:1")

    obj = runtime.create_or_refresh(spec, frame=1)
    runtime.extend_duration(
        type_key="barbara.ring",
        owner_key="slot:1",
        frames=120,
        max_extra_frames=300,
        frame=10,
    )
    assert obj.extra_duration_frames == 120

    refreshed = runtime.create_or_refresh(spec, frame=50)

    assert refreshed is not obj
    assert refreshed.extra_duration_frames == 0
    assert refreshed.entity.lifecycle.expires_at_frame == 150
    after = runtime.extend_duration(
        type_key="barbara.ring",
        owner_key="slot:1",
        frames=60,
        max_extra_frames=300,
        frame=60,
    )
    assert after is not None
    assert after.applied_frames == 60
    assert refreshed.entity.lifecycle.expires_at_frame == 210


def test_created_object_runtime_extension_ignores_missing_or_expired_object():
    type_impl = RecordingCreatedEntityType("barbara.ring")
    runtime = CreatedObjectRuntime({"barbara.ring": type_impl})
    spec = CreatedObjectSpec(type_key="barbara.ring", duration_frames=10, owner_key="slot:1")

    runtime.create_or_refresh(spec, frame=1)
    wrong_owner = runtime.extend_duration(
        type_key="barbara.ring",
        owner_key="slot:2",
        frames=60,
        max_extra_frames=300,
        frame=2,
    )
    unknown = runtime.extend_duration(
        type_key="other.object",
        owner_key="slot:1",
        frames=60,
        max_extra_frames=300,
        frame=2,
    )
    expired = runtime.extend_duration(
        type_key="barbara.ring",
        owner_key="slot:1",
        frames=60,
        max_extra_frames=300,
        frame=12,
    )

    assert wrong_owner is None
    assert unknown is None
    assert expired is None
    assert runtime.extension_records == ()


def test_created_object_runtime_aligns_tick_schedules_phase_preserving():
    # 重锚把全部调度按同一偏移平移：相对间隔（相位）不变，最早一拍落在目标帧。
    ctx = SimulationContext()
    type_impl = RecordingCreatedEntityType(
        "created.rotor",
        schedule_seeds=(
            ("a", 100, 50),
            ("b", 130, 70),
        ),
    )
    runtime = CreatedObjectRuntime({"created.rotor": type_impl})
    spec = CreatedObjectSpec(type_key="created.rotor", duration_frames=1000, owner_key="slot:1")
    obj = runtime.create_or_refresh(spec, frame=1)

    record = runtime.align_tick_schedules(
        type_key="created.rotor",
        owner_key="slot:1",
        target_frame=60,
        frame=10,
    )

    assert record is not None
    assert record.type_key == "created.rotor"
    assert record.earliest_tick_frame_before == 101
    assert record.target_tick_frame == 60
    assert record.delta_frames == -41
    schedules = {s.schedule_key: s.next_tick_frame for s in obj.schedules}
    # a 提前到 60，b 保持 +30 相位；间隔（a→b=30、周期 50/70）不变。
    assert schedules == {"a": 60, "b": 90}
    runtime.update_frame(ctx, 60)
    assert type_impl.calls[0] == (obj.entity.entity_id, 60, "a")
    assert len(runtime.tick_align_records) == 1


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


def test_created_object_runtime_align_rejects_past_target_and_missing_object():
    type_impl = RecordingCreatedEntityType(
        "created.rotor",
        schedule_seeds=(("a", 100, None),),
    )
    runtime = CreatedObjectRuntime({"created.rotor": type_impl})
    runtime.create_or_refresh(
        CreatedObjectSpec(type_key="created.rotor", duration_frames=1000, owner_key="slot:1"),
        frame=1,
    )

    missing = runtime.align_tick_schedules(
        type_key="created.rotor",
        owner_key="slot:2",
        target_frame=50,
        frame=10,
    )
    with pytest.raises(ValueError, match="不能早于当前帧"):
        runtime.align_tick_schedules(
            type_key="created.rotor",
            owner_key="slot:1",
            target_frame=5,
            frame=10,
        )

    assert missing is None
    assert runtime.tick_align_records == ()


def test_created_object_runtime_align_stopped_schedules_returns_none():
    # 全部调度无下一拍（一次性 tick 已消费）时无可重锚，返回 None。
    type_impl = RecordingCreatedEntityType(
        "created.once",
        schedule_seeds=(("a", 10, None),),
    )
    runtime = CreatedObjectRuntime({"created.once": type_impl})
    obj = runtime.create_or_refresh(
        CreatedObjectSpec(type_key="created.once", duration_frames=1000, owner_key="slot:1"),
        frame=1,
    )
    obj.schedules[0].next_tick_frame = None

    record = runtime.align_tick_schedules(
        type_key="created.once",
        owner_key="slot:1",
        target_frame=50,
        frame=20,
    )

    assert record is None
    assert runtime.tick_align_records == ()
