from __future__ import annotations

import pytest

from genshin_sim.core.simulation import BasicRuntimeWorld, SimulationContext
from genshin_sim.core.space import CircleArea, SceneTarget, Space, Vector3


def test_vector3_measures_distance_on_xz_plane():
    origin = Vector3(0, 999, 0)
    target = Vector3(3, -999, 4)

    assert origin.distance_xz_to(target) == 5


def test_circle_area_contains_positions_on_xz_plane_and_ignores_y():
    area = CircleArea(center=Vector3(0, 0, 0), radius=5)

    assert area.contains(Vector3(3, 999, 4))
    assert not area.contains(Vector3(6, 0, 0))


def test_circle_area_rejects_negative_radius():
    with pytest.raises(ValueError, match="radius must be non-negative"):
        CircleArea(center=Vector3(), radius=-1)


def test_space_queries_targets_in_radius_using_xz_plane():
    near = SceneTarget("near", position=Vector3(3, 100, 4), level=90)
    far = SceneTarget("far", position=Vector3(6, 0, 0), level=90)
    space = Space([near, far])

    assert space.targets_in_radius(Vector3(0, 0, 0), 5) == (near,)
    assert space.get_target("near") is near
    assert space.get_target("missing") is None


def test_space_queries_targets_in_area_preserving_insertion_order():
    first = SceneTarget("first", position=Vector3(1, 0, 0))
    second = SceneTarget("second", position=Vector3(2, 0, 0))
    space = Space([first, second])

    assert space.targets_in_area(CircleArea(center=Vector3(), radius=10)) == (first, second)


def test_space_rejects_duplicate_target_ids():
    space = Space([SceneTarget("target_1", position=Vector3())])

    with pytest.raises(ValueError, match="duplicate target id: target_1"):
        space.add_target(SceneTarget("target_1", position=Vector3(1, 0, 0)))


def test_space_can_be_attached_to_simulation_context_and_runtime_world():
    ctx = SimulationContext()
    space = Space([SceneTarget("target_1", position=Vector3())])
    ctx.space = space
    runtime_world = BasicRuntimeWorld([space])

    runtime_world.update_frame(ctx, frame=1)

    assert ctx.space is space
    assert runtime_world.is_idle()
