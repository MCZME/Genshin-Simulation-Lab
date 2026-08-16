from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.analysis.processors.comparison import (
    ComparisonError,
    ComparisonQuery,
    build_comparison,
)
from genshin_sim.analysis.processors.query import EventQuery, StateQuery
from genshin_sim.analysis.processors.state_fold import RecordedEventLike


class _FakeRun:
    def __init__(
        self,
        *,
        initial_snapshot: dict[str, object] | None,
        events: tuple[dict[str, Any], ...],
    ) -> None:
        self._initial_snapshot = initial_snapshot
        self._events = tuple(
            type(
                "Event",
                (),
                {
                    "frame": item["frame"],
                    "event_type": item["event_type"],
                    "data": item["data"],
                },
            )()
            for item in events
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


def _reader() -> _FakeReader:
    return _FakeReader(
        {
            "run:a": _FakeRun(
                initial_snapshot={
                    "providers": {
                        "team": {
                            "active_slot": 1,
                            "characters": [
                                {
                                    "slot": 1,
                                    "combat_entity_id": "character:slot_1",
                                    "current_hp": 7000.0,
                                }
                            ],
                        }
                    }
                },
                events=(
                    {
                        "frame": 2,
                        "event_type": "DAMAGE_RESOLVED",
                        "data": {"result": {"final_damage": 300.0}},
                    },
                ),
            ),
            "run:b": _FakeRun(
                initial_snapshot={
                    "providers": {
                        "team": {
                            "active_slot": 2,
                            "characters": [
                                {
                                    "slot": 1,
                                    "combat_entity_id": "character:slot_1",
                                    "current_hp": 9000.0,
                                }
                            ],
                        }
                    }
                },
                events=(),
            ),
        }
    )


def test_build_comparison_juxtaposes_state_and_event_queries():
    reader = _reader()
    queries = (
        ComparisonQuery(
            label="run_a_hp",
            query=StateQuery(
                session_ids=("run:a",),
                frames=(0,),
                paths=("team.characters[slot=1].current_hp",),
            ),
        ),
        ComparisonQuery(
            label="run_b_active",
            query=StateQuery(
                session_ids=("run:b",),
                frames=(0,),
                paths=("team.active_slot",),
            ),
        ),
        ComparisonQuery(
            label="run_a_damage",
            query=EventQuery(
                session_id="run:a",
                event_types=("DAMAGE_RESOLVED",),
                payload_path="result.final_damage",
            ),
        ),
    )

    result = build_comparison(reader, queries)

    assert [column.label for column in result.columns] == [
        "run_a_hp",
        "run_b_active",
        "run_a_damage",
    ]
    assert result.columns[0].results[0].value == 7000.0
    assert result.columns[1].results[0].value == 2
    assert result.columns[2].results[0].value == 300.0
    payload = result.to_dict()
    columns = cast(tuple[dict[str, object], ...], payload["columns"])
    assert columns[0]["label"] == "run_a_hp"


def test_build_comparison_validates_queries_and_labels():
    with pytest.raises(ComparisonError, match="至少需要一个查询"):
        build_comparison(_reader(), ())
    with pytest.raises(ComparisonError, match="重复"):
        build_comparison(
            _reader(),
            (
                ComparisonQuery(
                    "a",
                    StateQuery(("run:a",), (0,), ("team.active_slot",)),
                ),
                ComparisonQuery(
                    "a",
                    StateQuery(("run:b",), (0,), ("team.active_slot",)),
                ),
            ),
        )
    with pytest.raises(ComparisonError, match="非空字符串"):
        build_comparison(
            _reader(),
            (ComparisonQuery("", StateQuery(("run:a",), (0,), ("team.active_slot",))),),
        )
