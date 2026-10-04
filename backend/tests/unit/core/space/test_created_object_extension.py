# 单一关注点：创建物持续时间的延长（EXTEND_CREATED_ENTITY）与额度约束。
# 覆盖：单次延长与封顶、剩余额度递减、刷新重置已用额度、归属/类型未命中与
# 已过期对象一律忽略且不记审计记录。
from __future__ import annotations

from genshin_sim.core.space import CreatedObjectRuntime, CreatedObjectSpec
from tests.helpers.space import RecordingCreatedEntityType


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
