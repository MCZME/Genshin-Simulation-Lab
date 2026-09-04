from __future__ import annotations

from genshin_sim.core.elements import ElementalSubjectRef
from genshin_sim.core.systems.aura_icd import AuraIcdAttackerRef, IcdKey, IcdRecord, IcdSnapshot


def test_icd_snapshot_to_dict():
    key = IcdKey(
        attacker_ref=AuraIcdAttackerRef("attacker:1"),
        defender_ref=ElementalSubjectRef.target("target:1"),
        tag_key="tag",
        sequence_key="seq",
    )
    record = IcdRecord(
        key=key,
        window_started_frame=0,
        resets_at_frame=10,
        next_sequence_index=1,
        last_hit_frame=5,
        revision=2,
    )
    snapshot = IcdSnapshot(frame=5, normalized_through_frame=5, records=(record,))

    payload = snapshot.to_dict()

    assert payload == {
        "frame": 5,
        "normalized_through_frame": 5,
        "records": [
            {
                "key": {
                    "attacker_ref": {"scope_key": "attacker:1"},
                    "defender_ref": {"kind": "target", "entity_id": "target:1"},
                    "tag_key": "tag",
                    "sequence_key": "seq",
                },
                "window_started_frame": 0,
                "resets_at_frame": 10,
                "next_sequence_index": 1,
                "last_hit_frame": 5,
                "revision": 2,
            }
        ],
    }
