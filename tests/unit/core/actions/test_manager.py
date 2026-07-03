from __future__ import annotations

import pytest

from genshin_sim.core.actions import ActionManager, ActionRejectReason, ActionRequest, TargetQuery
from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.space import SceneTarget, Space, Vector3


def test_action_manager_accepts_request_and_reserves_busy_window():
    ctx = SimulationContext()
    events: list[GameEvent] = []
    ctx.events.subscribe(EventType.ACTION_DECISION, events.append)
    manager = ActionManager()

    decision = manager.request_action(
        ctx,
        ActionRequest(
            frame=10,
            key="keyboard.e",
            active_slot=2,
            duration_frames=2,
        )
    )

    assert decision.accepted
    assert decision.reject_reason is None
    assert decision.lock is not None
    assert decision.occupied_until_frame == 12
    assert manager.is_busy(10)
    assert manager.is_busy(11)
    assert not manager.is_busy(12)
    assert [event.data for event in events] == [
        {
            "key": "keyboard.e",
            "active_slot": 2,
            "accepted": True,
            "reject_reason": None,
            "occupied_until_frame": 12,
            "lock_source": "keyboard.e",
            "target_ids": (),
        }
    ]


def test_action_manager_is_updatable_until_locks_end():
    ctx = SimulationContext()
    manager = ActionManager()

    manager.reserve(
        frame=1,
        duration_frames=3,
        source="keyboard.e",
        active_slot=1,
    )

    assert not manager.is_idle()

    manager.update_frame(ctx, 1)
    assert not manager.is_idle()

    manager.update_frame(ctx, 3)
    assert not manager.is_idle()

    manager.update_frame(ctx, 4)
    assert manager.is_idle()


def test_action_manager_tracks_active_instances_until_they_end():
    ctx = SimulationContext()
    manager = ActionManager()

    decision = manager.request_action(
        ctx,
        ActionRequest(
            frame=1,
            key="keyboard.e",
            active_slot=1,
            duration_frames=2,
        ),
    )

    assert decision.instance is not None
    assert manager.instances == (decision.instance,)

    manager.update_frame(ctx, 1)
    assert manager.active_instances == (decision.instance,)

    manager.update_frame(ctx, 2)
    assert manager.active_instances == (decision.instance,)

    manager.update_frame(ctx, 3)
    assert manager.active_instances == ()
    assert manager.is_idle()


def test_action_manager_records_target_candidates_from_space_query():
    ctx = SimulationContext()
    events: list[GameEvent] = []
    ctx.events.subscribe(EventType.ACTION_DECISION, events.append)
    ctx.space = Space(
        [
            SceneTarget("near", position=Vector3(3, 999, 4)),
            SceneTarget("far", position=Vector3(6, 0, 0)),
        ]
    )
    manager = ActionManager()

    decision = manager.request_action(
        ctx,
        ActionRequest(
            frame=1,
            key="keyboard.e",
            active_slot=1,
            target_query=TargetQuery(origin=Vector3(0, 0, 0), radius=5),
        ),
    )

    assert decision.accepted
    assert decision.instance is not None
    assert decision.instance.target_ids == ("near",)
    assert events[0].data["target_ids"] == ("near",)


def test_action_manager_accepts_target_query_without_space_with_empty_candidates():
    ctx = SimulationContext()
    manager = ActionManager()

    decision = manager.request_action(
        ctx,
        ActionRequest(
            frame=1,
            key="keyboard.e",
            active_slot=1,
            target_query=TargetQuery(origin=Vector3(), radius=5),
        ),
    )

    assert decision.accepted
    assert decision.instance is not None
    assert decision.instance.target_ids == ()


def test_target_query_rejects_negative_radius():
    with pytest.raises(ValueError, match="target query radius must be non-negative"):
        TargetQuery(origin=Vector3(), radius=-1)


def test_action_manager_rejects_request_while_busy_then_accepts_after_window():
    ctx = SimulationContext()
    manager = ActionManager()
    manager.reserve(
        frame=1,
        duration_frames=2,
        source="character_switch",
        active_slot=2,
    )

    rejected = manager.request_action(
        ctx,
        ActionRequest(
            frame=2,
            key="keyboard.e",
            active_slot=2,
        )
    )
    accepted = manager.request_action(
        ctx,
        ActionRequest(
            frame=3,
            key="keyboard.e",
            active_slot=2,
        )
    )

    assert not rejected.accepted
    assert rejected.reject_reason is ActionRejectReason.BUSY
    assert rejected.lock is not None
    assert rejected.lock.source == "character_switch"
    assert rejected.instance is None
    assert accepted.accepted
    assert accepted.instance is not None
    assert [decision.accepted for decision in manager.decisions] == [False, True]


def test_action_manager_rejects_unsupported_key_when_supported_keys_are_limited():
    ctx = SimulationContext()
    manager = ActionManager(supported_keys={"keyboard.e"})

    decision = manager.request_action(
        ctx,
        ActionRequest(
            frame=1,
            key="mouse.left",
            active_slot=1,
        )
    )

    assert not decision.accepted
    assert decision.reject_reason is ActionRejectReason.UNSUPPORTED
    assert manager.locks == ()


@pytest.mark.parametrize(
    "duration_frames",
    [0, -1],
)
def test_action_manager_rejects_non_positive_duration(duration_frames: int):
    ctx = SimulationContext()
    manager = ActionManager()

    with pytest.raises(ValueError, match="duration_frames must be positive"):
        manager.request_action(
            ctx,
            ActionRequest(
                frame=1,
                key="keyboard.e",
                active_slot=1,
                duration_frames=duration_frames,
            )
        )
