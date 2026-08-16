"""芭芭拉安可被动的纵向集成：挂载、延长与上限。"""

from __future__ import annotations

import pytest

from genshin_sim.content import BARBARA_RING_OBJECT_KEY
from tests.helpers import barbara as barbara_helpers


def test_barbara_encore_effect_mounts_hook_from_asset_payload(barbara_assembled):
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


@pytest.mark.parametrize(
    ("count", "extra_frames"),
    (
        pytest.param(1, 60, id="single_particle"),
        pytest.param(3, 180, id="three_particles"),
    ),
)
def test_barbara_encore_particle_pickup_extends_ring_per_particle(
    barbara_assembled,
    count: int,
    extra_frames: int,
):
    assembled = barbara_assembled(input_key="keyboard.e", max_frames=80)
    barbara_helpers.spawn_barbara_pickup(
        assembled,
        request_id=f"encore:{count}",
        settle_frame=70,
        count=count,
    )

    assembled.simulator.run()

    ring = assembled.space_runtime.created_object_runtime.objects[0]
    assert ring.object_key == BARBARA_RING_OBJECT_KEY
    assert ring.extra_duration_frames == extra_frames
    records = assembled.space_runtime.created_object_runtime.extension_records
    assert [(record.requested_frames, record.applied_frames) for record in records] == [
        (extra_frames, extra_frames)
    ]
    assert len(assembled.impact_request_dispatcher.created_object_extension_records) == 1


def test_barbara_encore_extension_caps_at_five_seconds_per_ring(
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
    assert ring.extra_duration_frames == 300
    assert ring.entity.lifecycle.expires_at_frame == (
        ring.entity.lifecycle.created_frame + 907 + 300
    )
    records = assembled.space_runtime.created_object_runtime.extension_records
    assert [record.applied_frames for record in records] == [60, 60, 60, 60, 60, 0]
    assert sum(record.applied_frames for record in records) == 300
