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
            RecordedEvent(
                frame=2,
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
                source_type="HealthRuntime",
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
    assert items[0].event_count == 2
    assert detail.summary.frames_run == 120
    assert detail.events[0].data == {"ok": True}
    assert detail.events[1].event_type == "CHARACTER_HEALTH_CHANGED"
    assert detail.events[1].data["result"]["hp_after"] == 700
