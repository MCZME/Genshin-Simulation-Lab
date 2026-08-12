from __future__ import annotations

import sqlite3

import pytest

from genshin_sim.application.execution import (
    CompletedSimulationRun,
    FailedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.infrastructure.results_sqlite import SQLiteResultRepository, SQLiteResultWriter
from genshin_sim.infrastructure.results_sqlite.repository import ResultNotFoundError
from genshin_sim.infrastructure.results_sqlite.schema import (
    RESULTS_SCHEMA_VERSION,
    init_result_database,
)


def test_result_writer_and_repository_round_trip_completed_run(tmp_path):
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    run = CompletedSimulationRun(
        input_schema_version=2,
        input_kind="simulation_input",
        input_meta={"name": "Smoke Run"},
        input_snapshot={"schema_version": 2, "kind": "simulation_input"},
        summary=SimulationRunSummary(
            stop_reason="MAX_FRAMES",
            end_frame=120,
            frames_run=120,
        ),
        events=(
            RecordedEvent(
                frame=1,
                event_type="SIMULATION_STARTED",
                data={"ok": True},
            ),
            RecordedEvent(
                frame=2,
                event_type="HEALING_RESOLVED",
                data={
                    "result": {
                        "healing_id": "healing:1",
                        "frame": 2,
                        "source_ref": {
                            "kind": "character",
                            "entity_id": "character:slot_1",
                        },
                        "target_ref": {
                            "kind": "character",
                            "entity_id": "character:slot_1",
                        },
                        "component_results": [
                            {
                                "component_key": "hp",
                                "attribute_key": "stat.hp.max",
                                "scaling_value": 1000,
                                "coefficient": 0.1,
                                "value": 100,
                            }
                        ],
                        "flat_healing": 0,
                        "base_healing": 100,
                        "outgoing_healing_bonus": 0,
                        "incoming_healing_bonus": 0,
                        "healing_bonus_multiplier": 1,
                        "final_healing": 100,
                    }
                },
            ),
            RecordedEvent(
                frame=3,
                event_type="CHARACTER_HEALTH_CHANGED",
                data={
                    "result": {
                        "change_id": "health:1",
                        "change_kind": "damage",
                        "target_ref": {
                            "kind": "character",
                            "entity_id": "character:slot_1",
                        },
                        "requested_amount": 300,
                        "effective_amount": 300,
                        "unapplied_amount": 0,
                        "hp_before": 1000,
                        "hp_after": 700,
                        "max_hp": 1000,
                        "minimum_remaining_hp": None,
                    }
                },
            ),
        ),
        initial_snapshot={"frame": 0, "events": [], "providers": {}},
        created_at="2026-07-04T00:00:00+00:00",
        started_at="2026-07-04T00:00:00+00:00",
        finished_at="2026-07-04T00:00:30+00:00",
    )

    session_id = writer.save_run(run)
    repository = SQLiteResultRepository(db_path)

    items = repository.list_runs()
    detail = repository.get_run(session_id)

    assert items[0].session_id == session_id
    assert items[0].name == "Smoke Run"
    assert items[0].event_count == 3
    assert detail.summary is not None
    assert detail.summary.frames_run == 120
    assert detail.events[0].data == {"ok": True}
    assert detail.events[1].event_type == "HEALING_RESOLVED"
    assert detail.events[1].data["result"]["final_healing"] == 100
    assert detail.events[2].event_type == "CHARACTER_HEALTH_CHANGED"
    assert detail.events[2].data["result"]["hp_after"] == 700
    assert detail.state == "completed"
    assert detail.initial_snapshot == {"frame": 0, "events": [], "providers": {}}
    assert detail.started_at is not None
    assert detail.finished_at is not None
    assert "source_type" not in detail.events[0].to_dict()
    assert RESULTS_SCHEMA_VERSION == "2"


def test_failed_run_round_trip(tmp_path):
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    failed = FailedSimulationRun(
        session_id="failed-session",
        input_schema_version=2,
        input_kind="simulation_input",
        input_meta={"name": "Failed Run"},
        input_snapshot={"schema_version": 2, "kind": "simulation_input"},
        error_code="RuntimeError",
        error_message="boom",
    )

    session_id = writer.save_failed_run(failed)
    repository = SQLiteResultRepository(db_path)
    detail = repository.get_run(session_id)

    assert detail.state == "failed"
    assert detail.summary is None
    assert detail.events == ()
    assert detail.error_code == "RuntimeError"
    assert detail.error_message == "boom"
    items = repository.list_runs()
    assert items[0].state == "failed"
    assert items[0].event_count == 0


def test_duplicate_session_write_rejected(tmp_path):
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    run = CompletedSimulationRun(
        input_schema_version=2,
        input_kind="simulation_input",
        input_meta={"name": "Dup"},
        input_snapshot={"schema_version": 2, "kind": "simulation_input"},
        summary=SimulationRunSummary(
            stop_reason="MAX_FRAMES",
            end_frame=1,
            frames_run=1,
        ),
        events=(),
    )

    writer.save_run(run)

    with pytest.raises(ValueError, match="already exists"):
        writer.save_run(run)


def test_get_events_filters_and_paginates(tmp_path):
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    run = CompletedSimulationRun(
        input_schema_version=2,
        input_kind="simulation_input",
        input_meta={"name": "Events"},
        input_snapshot={"schema_version": 2, "kind": "simulation_input"},
        summary=SimulationRunSummary(
            stop_reason="MAX_FRAMES",
            end_frame=4,
            frames_run=4,
        ),
        events=(
            RecordedEvent(frame=1, event_type="INPUT_KEY_RECEIVED", data={"key": "keyboard.e"}),
            RecordedEvent(frame=2, event_type="DAMAGE_RESOLVED", data={"damage": 100}),
            RecordedEvent(frame=3, event_type="INPUT_KEY_RECEIVED", data={"key": "keyboard.q"}),
            RecordedEvent(frame=4, event_type="DAMAGE_RESOLVED", data={"damage": 50}),
        ),
    )
    session_id = writer.save_run(run)
    repository = SQLiteResultRepository(db_path)

    assert [event.frame for event in repository.get_events(session_id, frame_min=3)] == [3, 4]
    assert [event.frame for event in repository.get_events(session_id, frame_max=2)] == [1, 2]
    assert [
        event.frame for event in repository.get_events(session_id, frame_min=2, frame_max=3)
    ] == [
        2,
        3,
    ]
    assert [
        event.event_type
        for event in repository.get_events(session_id, event_type="DAMAGE_RESOLVED")
    ] == ["DAMAGE_RESOLVED", "DAMAGE_RESOLVED"]
    assert [event.frame for event in repository.get_events(session_id, offset=1, limit=2)] == [
        2,
        3,
    ]
    assert [event.frame for event in repository.get_events(session_id, offset=2)] == [3, 4]
    assert repository.get_events(session_id, event_type="NO_SUCH_EVENT") == ()

    with pytest.raises(ResultNotFoundError):
        repository.get_events("missing-session")


def test_list_runs_filters_by_state(tmp_path):
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    writer.save_run(
        CompletedSimulationRun(
            input_schema_version=2,
            input_kind="simulation_input",
            input_meta={"name": "Completed"},
            input_snapshot={"schema_version": 2, "kind": "simulation_input"},
            summary=SimulationRunSummary(
                stop_reason="MAX_FRAMES",
                end_frame=1,
                frames_run=1,
            ),
            events=(),
        )
    )
    writer.save_failed_run(
        FailedSimulationRun(
            session_id="failed-1",
            input_schema_version=2,
            input_kind="simulation_input",
            input_meta={"name": "Failed"},
            input_snapshot={"schema_version": 2, "kind": "simulation_input"},
            error_message="boom",
        )
    )
    repository = SQLiteResultRepository(db_path)

    failed_items = repository.list_runs(state="failed")
    all_items = repository.list_runs()

    assert [item.session_id for item in failed_items] == ["failed-1"]
    assert {item.state for item in all_items} == {"failed", "completed"}


def test_init_result_database_rejects_incompatible_existing_schema(tmp_path):
    db_path = tmp_path / "results.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE result_db_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO result_db_meta(key, value) VALUES ('schema_version', '1');
        """
    )
    connection.commit()
    connection.close()

    with pytest.raises(ValueError, match="schema 版本不兼容"):
        init_result_database(db_path)

    stored = dict(
        sqlite3.connect(db_path)
        .execute("SELECT key, value FROM result_db_meta")
        .fetchall()
    )
    assert stored["schema_version"] == "1"


def test_init_result_database_allows_same_version_reinit(tmp_path):
    db_path = tmp_path / "results.db"
    init_result_database(db_path)

    init_result_database(db_path)

    stored = dict(
        sqlite3.connect(db_path)
        .execute("SELECT key, value FROM result_db_meta")
        .fetchall()
    )
    assert stored["schema_version"] == RESULTS_SCHEMA_VERSION
