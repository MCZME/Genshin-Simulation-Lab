from __future__ import annotations

from genshin_sim.core.space.entities import SpatialEntity, SpatialEntityKind
from genshin_sim.core.space.geometry import Vector3
from genshin_sim.core.space.space import Space


def test_space_snapshot_to_dict_is_serializable():
    space = Space()
    space.add_entity(
        SpatialEntity(
            entity_id="target:1",
            kind=SpatialEntityKind.TARGET,
            position=Vector3(0.0, 0.0, 5.0),
        )
    )

    payload = space.snapshot(0).to_dict()

    assert payload["frame"] == 0
    assert payload["entities"] == [
        {
            "entity_id": "target:1",
            "kind": "target",
            "position": {"x": 0.0, "y": 0.0, "z": 5.0},
            "lifecycle": {
                "created_frame": 0,
                "expires_at_frame": None,
                "state": "active",
            },
            "collision_box": {"shape": "圆柱", "radius": 0.5, "height": 1.0},
            "facing": {"x": 0.0, "y": 0.0, "z": 1.0},
            "active_slot": None,
            "owner_key": None,
            "source_key": None,
            "tags": [],
        }
    ]
