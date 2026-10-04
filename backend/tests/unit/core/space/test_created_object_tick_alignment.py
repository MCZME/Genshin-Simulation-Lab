# 单一关注点：创建物 tick 调度的重锚（ALIGN_CREATED_ENTITY_TICKS）。
# 覆盖：相位保持的平移与审计记录、目标帧早于当前帧与对象缺失的拒绝分支、
# 全部调度已停机时无可重锚返回 None。
from __future__ import annotations

import pytest

from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.space import CreatedObjectRuntime, CreatedObjectSpec
from tests.helpers.space import RecordingCreatedEntityType


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
