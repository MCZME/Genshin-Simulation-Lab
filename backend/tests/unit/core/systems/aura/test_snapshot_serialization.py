from __future__ import annotations

from genshin_sim.core.systems.aura import AuraSnapshot


def test_aura_snapshot_to_dict():
    snapshot = AuraSnapshot(frame=0, normalized_through_frame=0, targets=())

    assert snapshot.to_dict() == {"frame": 0, "normalized_through_frame": 0, "targets": []}
