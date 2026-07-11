from __future__ import annotations

from genshin_sim.core.events import EventType, GameEvent, InputKeyReceivedPayload
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.snapshots import EventSnapshot, SimulationSnapshot, export_snapshot


def test_snapshot_exports_current_frame_events():
    ctx = SimulationContext()
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
    ctx.events.publish(event)

    snapshot = export_snapshot(ctx, meta={"run_id": "demo"})

    assert snapshot.frame == 0
    assert snapshot.events == (EventSnapshot.from_event(event),)
    assert snapshot.meta == {"run_id": "demo"}


def test_snapshot_to_dict_is_serializable():
    snapshot = SimulationSnapshot(
        frame=1,
        events=(
            EventSnapshot(
                event_type="INPUT_KEY_RECEIVED",
                frame=1,
                data={"key": "keyboard.e", "phase": "press", "order": 0, "session_id": 1},
            ),
        ),
        meta={"name": "demo"},
    )

    assert snapshot.to_dict()["events"][0]["event_type"] == "INPUT_KEY_RECEIVED"
