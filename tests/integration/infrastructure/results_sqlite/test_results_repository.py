from __future__ import annotations

from genshin_sim.application.execution import (
    CompletedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.infrastructure.results_sqlite import SQLiteResultRepository, SQLiteResultWriter


def test_result_writer_and_repository_round_trip_completed_run(tmp_path):
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    run = CompletedSimulationRun(
        config_schema_version=1,
        config_kind="simulation_config",
        config_meta={"name": "Smoke Run"},
        config_snapshot={"schema_version": 1, "kind": "simulation_config"},
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
                source_type="Simulator",
            ),
        ),
        created_at="2026-07-04T00:00:00+00:00",
    )

    session_id = writer.save_run(run)
    repository = SQLiteResultRepository(db_path)

    items = repository.list_runs()
    detail = repository.get_run(session_id)

    assert items[0].session_id == session_id
    assert items[0].name == "Smoke Run"
    assert items[0].event_count == 1
    assert detail.summary.frames_run == 120
    assert detail.events[0].data == {"ok": True}
