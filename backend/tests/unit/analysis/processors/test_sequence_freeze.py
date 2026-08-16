from __future__ import annotations

from genshin_sim.analysis.processors.sequences import (
    DamageSequenceEntry,
    HealingSequenceEntry,
)


def test_damage_sequence_entry_fields_are_frozen():
    entry = DamageSequenceEntry(
        frame=1,
        damage_id="damage:1",
        source_ref="character:slot_1",
        target_ref="target:target_1",
        amount=300.0,
        damage_kind="skill",
        event_ref=0,
    )

    assert tuple(entry.to_dict()) == (
        "frame",
        "damage_id",
        "source_ref",
        "target_ref",
        "amount",
        "damage_kind",
        "event_ref",
    )


def test_healing_sequence_entry_fields_are_frozen():
    entry = HealingSequenceEntry(
        frame=1,
        healing_id="healing:1",
        source_ref="character:slot_1",
        target_ref="character:slot_2",
        amount=120.0,
        healing_kind="healing",
        event_ref=0,
    )

    assert tuple(entry.to_dict()) == (
        "frame",
        "healing_id",
        "source_ref",
        "target_ref",
        "amount",
        "healing_kind",
        "event_ref",
    )
