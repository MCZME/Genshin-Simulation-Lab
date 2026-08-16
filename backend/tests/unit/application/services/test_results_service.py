from __future__ import annotations

from typing import cast

from genshin_sim.analysis.processors.comparison import ComparisonQuery
from genshin_sim.analysis.processors.query import EventQuery, StateQuery
from genshin_sim.application.execution.models import RecordedEvent, SimulationRunSummary
from genshin_sim.application.services import (
    ResultDatabaseService,
    ResultsService,
)
from genshin_sim.application.services.models import RunDetail
from genshin_sim.application.services.protocols import ResultRepository


def test_result_database_service_delegates_initialization(tmp_path):
    calls: list[str] = []

    def init_database(path):
        calls.append(str(path))
        return path

    db_path = tmp_path / "results.db"
    service = ResultDatabaseService(init_database)

    assert service.init_database(db_path) == db_path
    assert calls == [str(db_path)]


class _FakeResultRepository:
    def __init__(self, run: RunDetail) -> None:
        self._run = run

    def get_run(self, session_id: str) -> RunDetail:
        assert session_id == "run:1"
        return self._run

    def list_runs(self, limit: int = 50, state: str | None = None) -> tuple[object, ...]:
        return ()

    def get_events(self, session_id: str, **kwargs: object) -> tuple[RecordedEvent, ...]:
        return self._run.events


class _FakeMultiRunRepository(_FakeResultRepository):
    def __init__(self, runs: dict[str, RunDetail]) -> None:
        self._runs = runs

    def get_run(self, session_id: str) -> RunDetail:
        return self._runs[session_id]

    def get_events(self, session_id: str, **kwargs: object) -> tuple[RecordedEvent, ...]:
        return self._runs[session_id].events


def test_results_service_folds_state_through_analysis():
    run = RunDetail(
        session_id="run:1",
        state="completed",
        input_snapshot={},
        initial_snapshot={
            "providers": {
                "team": {
                    "active_slot": 1,
                    "characters": [
                        {
                            "combat_entity_id": "character:slot_1",
                            "current_hp": 10000.0,
                        }
                    ],
                }
            }
        },
        summary=None,
        events=(
            RecordedEvent(
                frame=5,
                event_type="CHARACTER_HEALTH_CHANGED",
                data={
                    "result": {
                        "target_ref": {
                            "kind": "character",
                            "entity_id": "character:slot_1",
                        },
                        "hp_after": 500.0,
                    }
                },
            ),
        ),
        error_code=None,
        error_message=None,
        created_at="2026-08-11T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )
    service = ResultsService(cast(ResultRepository, _FakeResultRepository(run)))

    view = service.fold_state("run:1", frame=5)

    team = cast(dict[str, object], view.providers["team"])
    character = cast(dict[str, object], cast(list[object], team["characters"])[0])
    assert character["current_hp"] == 500.0
    assert view.fold_status["team"] == "folded"


def test_results_service_queries_state_and_events():
    run = RunDetail(
        session_id="run:1",
        state="completed",
        input_snapshot={},
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
        summary=None,
        events=(
            RecordedEvent(
                frame=2,
                event_type="DAMAGE_RESOLVED",
                data={"result": {"final_damage": 300.0}},
            ),
        ),
        error_code=None,
        error_message=None,
        created_at="2026-08-11T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )
    service = ResultsService(cast(ResultRepository, _FakeResultRepository(run)))

    state_results = service.query_state(
        StateQuery(
            session_ids=("run:1",),
            frames=(0,),
            paths=("team.active_slot",),
        )
    )
    event_results = service.query_events(
        EventQuery(
            session_id="run:1",
            event_types=("DAMAGE_RESOLVED",),
            payload_path="result.final_damage",
        )
    )

    assert state_results[0].value == 1
    assert event_results[0].value == 300.0
    assert event_results[0].ordinal == 0


def test_results_service_computes_damage_metrics():
    run = RunDetail(
        session_id="run:1",
        state="completed",
        input_snapshot={},
        initial_snapshot=None,
        summary=SimulationRunSummary(
            stop_reason="COMPLETED",
            end_frame=60,
            frames_run=60,
        ),
        events=(
            RecordedEvent(
                frame=10,
                event_type="DAMAGE_RESOLVED",
                data={
                    "result": {
                        "request_id": "damage:1",
                        "source_ref": "character:slot_1",
                        "target_ref": "target:target_1",
                        "final_damage": 300.0,
                        "damage_type": "skill",
                    }
                },
            ),
        ),
        error_code=None,
        error_message=None,
        created_at="2026-08-11T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )
    service = ResultsService(cast(ResultRepository, _FakeResultRepository(run)))

    metrics = service.damage_metrics("run:1")

    assert metrics.total_damage.value == 300.0
    assert metrics.dps.value == 300.0
    assert metrics.damage_share_by_source[0].group == "character:slot_1"


def test_results_service_compares_queries():
    def _run(session_id: str, active_slot: int) -> RunDetail:
        return RunDetail(
            session_id=session_id,
            state="completed",
            input_snapshot={},
            initial_snapshot={
                "providers": {
                    "team": {
                        "active_slot": active_slot,
                        "characters": [],
                    }
                }
            },
            summary=None,
            events=(),
            error_code=None,
            error_message=None,
            created_at="2026-08-11T00:00:00+00:00",
            started_at=None,
            finished_at=None,
        )

    service = ResultsService(
        cast(
            ResultRepository,
            _FakeMultiRunRepository(
                {
                    "run:1": _run("run:1", 1),
                    "run:2": _run("run:2", 2),
                }
            ),
        )
    )

    result = service.compare(
        (
            ComparisonQuery(
                "first",
                StateQuery(("run:1",), (0,), ("team.active_slot",)),
            ),
            ComparisonQuery(
                "second",
                StateQuery(("run:2",), (0,), ("team.active_slot",)),
            ),
        )
    )

    assert result.columns[0].results[0].value == 1
    assert result.columns[1].results[0].value == 2
