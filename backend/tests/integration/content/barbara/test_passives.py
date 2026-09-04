"""芭芭拉安可被动的纵向集成：挂载、延长与上限。"""

from __future__ import annotations

import pytest

from genshin_sim.content import BARBARA_RING_OBJECT_KEY
from tests.helpers import barbara as barbara_helpers


def test_barbara_encore_effect_mounts_hook_from_effect_payload(barbara_assembled):
    assembled = barbara_assembled(input_key="keyboard.e", max_frames=20)

    hooks = [
        hook
        for hook in assembled.content_bundle.event_hooks
        if hook.hook_key.startswith("barbara.encore")
    ]
    assert len(hooks) == 1
    assert hooks[0].subscriptions == ("ENERGY_PICKUP_SETTLED",)
    assert any(
        unit.handler_key == "character.barbara.passive.encore"
        for unit in assembled.content_bundle.content_units
    )


def test_barbara_encore_particle_pickup_extends_ring_per_particle(
    barbara_assembled,
):
    def _run(count: int) -> float:
        assembled = barbara_assembled(input_key="keyboard.e", max_frames=80)
        barbara_helpers.spawn_barbara_pickup(
            assembled,
            request_id=f"encore:{count}",
            settle_frame=70,
            count=count,
        )

        assembled.simulator.run()

        ring = assembled.space_runtime.created_object_runtime.objects[0]
        records = assembled.space_runtime.created_object_runtime.extension_records
        assert ring.object_key == BARBARA_RING_OBJECT_KEY
        assert len(records) == 1
        assert records[0].applied_frames == records[0].requested_frames
        assert len(assembled.impact_request_dispatcher.created_object_extension_records) == 1
        return ring.extra_duration_frames

    single = _run(1)
    triple = _run(3)
    assert triple == pytest.approx(3 * single)


def test_barbara_encore_extension_caps_per_ring(
    barbara_assembled,
):
    assembled = barbara_assembled(input_key="keyboard.e", max_frames=80)
    for index, settle_frame in enumerate((10, 20, 30, 40, 50, 60), start=1):
        barbara_helpers.spawn_barbara_pickup(
            assembled,
            request_id=f"encore:cap:{index}",
            settle_frame=settle_frame,
            count=1,
        )

    assembled.simulator.run()

    ring = assembled.space_runtime.created_object_runtime.objects[0]
    records = assembled.space_runtime.created_object_runtime.extension_records
    per_pickup = records[0].applied_frames
    assert per_pickup > 0
    assert [record.applied_frames for record in records] == [per_pickup] * 5 + [0]
    assert ring.extra_duration_frames == 5 * per_pickup
