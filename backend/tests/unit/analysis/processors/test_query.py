from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.analysis.processors.query import (
    EventQuery,
    QueryValidationError,
    StateQuery,
    query_events,
    query_state,
)
from genshin_sim.analysis.processors.state_fold import RecordedEventLike
from tests.helpers.analysis import recorded_event


class _FakeRun:
    def __init__(
        self,
        *,
        initial_snapshot: dict[str, object] | None,
        events: tuple[dict[str, Any], ...],
    ) -> None:
        self._initial_snapshot = initial_snapshot
        self._events = tuple(
            recorded_event(item["frame"], item["event_type"], item["data"]) for item in events
        )

    @property
    def initial_snapshot(self) -> dict[str, object] | None:
        return self._initial_snapshot

    @property
    def events(self) -> tuple[RecordedEventLike, ...]:
        return cast(tuple[RecordedEventLike, ...], self._events)


class _FakeReader:
    def __init__(self, runs: dict[str, _FakeRun]) -> None:
        self._runs = runs

    def get_run(self, session_id: str) -> _FakeRun:
        return self._runs[session_id]


def _run_a() -> _FakeRun:
    return _FakeRun(
        initial_snapshot={
            "providers": {
                "team": {
                    "active_slot": 1,
                    "characters": [
                        {
                            "slot": 1,
                            "combat_entity_id": "character:slot_1",
                            "current_hp": 10000.0,
                        }
                    ],
                }
            }
        },
        events=(
            {
                "frame": 1,
                "event_type": "CHARACTER_HEALTH_CHANGED",
                "data": {
                    "result": {
                        "target_ref": {
                            "kind": "character",
                            "entity_id": "character:slot_1",
                        },
                        "hp_after": 7000.0,
                    }
                },
            },
            {
                "frame": 2,
                "event_type": "DAMAGE_RESOLVED",
                "data": {
                    "result": {
                        "final_damage": 300.0,
                        "target_ref": {
                            "kind": "character",
                            "entity_id": "character:slot_1",
                        },
                    }
                },
            },
            {
                "frame": 3,
                "event_type": "DAMAGE_RESOLVED",
                "data": {
                    "result": {
                        "final_damage": 500.0,
                        "target_ref": {
                            "kind": "character",
                            "entity_id": "character:slot_2",
                        },
                    }
                },
            },
        ),
    )


def _run_b() -> _FakeRun:
    return _FakeRun(
        initial_snapshot={
            "providers": {
                "team": {
                    "active_slot": 2,
                    "characters": [
                        {
                            "slot": 1,
                            "combat_entity_id": "character:slot_1",
                            "current_hp": 5000.0,
                        }
                    ],
                }
            }
        },
        events=(),
    )


def test_query_state_supports_multi_session_multi_frame_multi_path():
    reader = _FakeReader({"run:a": _run_a(), "run:b": _run_b()})
    query = StateQuery(
        session_ids=("run:a", "run:b"),
        frames=(0, 1),
        paths=("team.active_slot", "team.characters[slot=1].current_hp"),
    )

    results = query_state(reader, query)

    assert [(item.session_id, item.frame, item.path) for item in results] == [
        ("run:a", 0, "team.active_slot"),
        ("run:a", 0, "team.characters[slot=1].current_hp"),
        ("run:a", 1, "team.active_slot"),
        ("run:a", 1, "team.characters[slot=1].current_hp"),
        ("run:b", 0, "team.active_slot"),
        ("run:b", 0, "team.characters[slot=1].current_hp"),
        ("run:b", 1, "team.active_slot"),
        ("run:b", 1, "team.characters[slot=1].current_hp"),
    ]
    values = {item.path: item.value for item in results if item.session_id == "run:a"}
    assert values["team.active_slot"] == 1
    assert values["team.characters[slot=1].current_hp"] == 7000.0


def test_query_events_filters_by_type_frame_payload_path_and_equality():
    reader = _FakeReader({"run:a": _run_a()})
    query = EventQuery(
        session_id="run:a",
        event_types=("DAMAGE_RESOLVED",),
        frame_min=1,
        frame_max=3,
        payload_path="result.final_damage",
        filters=(
            (
                "result.target_ref.entity_id",
                "character:slot_2",
            ),
        ),
    )

    results = query_events(reader, query)

    assert len(results) == 1
    assert results[0].ordinal == 2
    assert results[0].frame == 3
    assert results[0].value == 500.0


def test_query_events_supports_pagination():
    reader = _FakeReader({"run:a": _run_a()})
    query = EventQuery(
        session_id="run:a",
        event_types=("CHARACTER_HEALTH_CHANGED", "DAMAGE_RESOLVED"),
        offset=1,
        limit=1,
    )

    results = query_events(reader, query)

    assert len(results) == 1
    assert results[0].ordinal == 1
    assert results[0].event_type == "DAMAGE_RESOLVED"


def test_query_validation_rejects_invalid_conditions():
    with pytest.raises(QueryValidationError, match="session_ids"):
        StateQuery(session_ids=(), frames=(0,), paths=("team",))
    with pytest.raises(QueryValidationError, match="frames"):
        StateQuery(session_ids=("run:a",), frames=(), paths=("team",))
    with pytest.raises(QueryValidationError, match="event_types"):
        EventQuery(session_id="run:a", event_types=())
    with pytest.raises(QueryValidationError, match="frame_max"):
        EventQuery(
            session_id="run:a",
            event_types=("DAMAGE_RESOLVED",),
            frame_min=5,
            frame_max=3,
        )
    with pytest.raises(QueryValidationError, match="limit"):
        EventQuery(session_id="run:a", event_types=("DAMAGE_RESOLVED",), limit=0)
