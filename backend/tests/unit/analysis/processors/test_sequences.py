from __future__ import annotations

import pytest

from genshin_sim.analysis.processors.sequences import (
    SequenceError,
    build_damage_sequence,
    build_healing_sequence,
)
from tests.helpers.analysis import recorded_event


def test_build_damage_sequence_extracts_raw_fields_in_order():
    events = (
        recorded_event(
            1,
            "DAMAGE_RESOLVED",
            {
                "result": {
                    "request_id": "damage:1",
                    "source_ref": "character:slot_1",
                    "target_ref": "target:target_1",
                    "final_damage": 300.0,
                    "damage_type": "skill",
                }
            },
        ),
        recorded_event(2, "HEALING_RESOLVED", {"result": {"healing_id": "healing:1"}}),
        recorded_event(
            3,
            "DAMAGE_RESOLVED",
            {
                "result": {
                    "request_id": "damage:2",
                    "source_ref": "character:slot_2",
                    "target_ref": "target:target_1",
                    "final_damage": 500.0,
                    "damage_type": "burst",
                }
            },
        ),
    )

    sequence = build_damage_sequence(events)

    assert [entry.damage_id for entry in sequence] == ["damage:1", "damage:2"]
    assert [entry.event_ref for entry in sequence] == [0, 2]
    assert sequence[1].amount == 500.0
    assert sequence[1].damage_kind == "burst"
    assert sequence[0].target_ref == "target:target_1"


def test_build_healing_sequence_extracts_subject_entity_ids():
    events = (
        recorded_event(
            1,
            "HEALING_RESOLVED",
            {
                "result": {
                    "healing_id": "healing:1",
                    "source_ref": {"kind": "character", "entity_id": "character:slot_1"},
                    "target_ref": {"kind": "character", "entity_id": "character:slot_2"},
                    "final_healing": 120.0,
                }
            },
        ),
        recorded_event(2, "DAMAGE_RESOLVED", {"result": {"request_id": "damage:1"}}),
    )

    sequence = build_healing_sequence(events)

    assert len(sequence) == 1
    assert sequence[0].healing_id == "healing:1"
    assert sequence[0].source_ref == "character:slot_1"
    assert sequence[0].target_ref == "character:slot_2"
    assert sequence[0].amount == 120.0
    assert sequence[0].event_ref == 0


def test_build_sequences_raise_on_malformed_payload():
    with pytest.raises(SequenceError, match="result"):
        build_damage_sequence((recorded_event(1, "DAMAGE_RESOLVED", {}),))
    with pytest.raises(SequenceError, match="source_ref"):
        build_healing_sequence(
            (
                recorded_event(
                    1,
                    "HEALING_RESOLVED",
                    {"result": {"healing_id": "h:1", "source_ref": "x"}},
                ),
            )
        )
