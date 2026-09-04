from __future__ import annotations

import pytest

from genshin_sim.core.events import EventType, GameEvent, InputKeyReceivedPayload
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.snapshots import (
    DuplicateSnapshotProviderError,
    EventSnapshot,
    FrameSnapshot,
    SnapshotRuntime,
)


def _energy_snapshot(frame: int) -> dict[str, object]:
    return {"frame": frame, "characters": ()}


def test_snapshot_runtime_exports_frame_snapshot():
    runtime = SnapshotRuntime()
    runtime.register("energy", _energy_snapshot)

    snapshot = runtime.snapshot_frame(SimulationContext(), frame=3)

    assert isinstance(snapshot, FrameSnapshot)
    assert snapshot.frame == 3
    assert snapshot.providers == {"energy": {"frame": 3, "characters": ()}}
    assert runtime.snapshot_at(3) is snapshot
    assert runtime.snapshots == (snapshot,)


def test_snapshot_runtime_rejects_duplicate_provider():
    runtime = SnapshotRuntime()
    runtime.register("energy", _energy_snapshot)

    with pytest.raises(DuplicateSnapshotProviderError, match="energy"):
        runtime.register("energy", _energy_snapshot)


def test_snapshot_runtime_sorts_providers_by_key():
    runtime = SnapshotRuntime()
    runtime.register("buff", lambda frame: {"frame": frame})
    runtime.register("energy", _energy_snapshot)

    snapshot = runtime.snapshot_frame(SimulationContext(), frame=0)

    assert list(snapshot.providers) == ["buff", "energy"]


def test_frame_snapshot_rejects_negative_frame():
    with pytest.raises(ValueError, match="frame"):
        FrameSnapshot(frame=-1)


def test_event_snapshot_from_event():
    event = GameEvent(
        EventType.INPUT_KEY_RECEIVED,
        frame=2,
        payload=InputKeyReceivedPayload(
            key="keyboard.e",
            phase="press",
            order=0,
            session_id=1,
        ),
    )

    snapshot = EventSnapshot.from_event(event)

    assert snapshot.event_type == "INPUT_KEY_RECEIVED"
    assert snapshot.frame == 2
    assert snapshot.data == {
        "key": "keyboard.e",
        "phase": "press",
        "order": 0,
        "session_id": 1,
    }
    assert "source_type" not in snapshot.to_dict()
