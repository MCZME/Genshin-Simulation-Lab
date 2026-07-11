from __future__ import annotations

import json
from pathlib import Path
from time import monotonic, sleep

from genshin_sim.application.jobs import SimulationJobState
from genshin_sim.application.services import SimulationTaskService
from genshin_sim.infrastructure.assets_sqlite import write_minimal_static_asset_database
from genshin_sim.infrastructure.jobs import ProcessSimulationJobRunner
from genshin_sim.infrastructure.results_sqlite import SQLiteResultRepository


def test_process_runner_runs_file_and_persists_result(tmp_path: Path):
    asset_db = tmp_path / "assets.db"
    result_db = tmp_path / "results.db"
    config_path = tmp_path / "config.json"
    write_minimal_static_asset_database(asset_db)
    config_path.write_text(
        json.dumps(_minimal_config_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    with ProcessSimulationJobRunner(
        asset_db_path=asset_db,
        result_db_path=result_db,
        max_workers=1,
        job_id_factory=lambda: "job-1",
    ) as runner:
        service = SimulationTaskService(runner)

        result = service.run_file_and_wait(
            config_path,
            poll_interval_seconds=0.01,
            timeout_seconds=10,
        )

    assert result.state is SimulationJobState.COMPLETED
    assert result.session_id is not None
    assert result.summary is not None
    assert result.summary.frames_run == 3

    detail = SQLiteResultRepository(result_db).get_run(result.session_id)
    assert detail.summary.stop_reason == "COMPLETED"
    assert detail.config_snapshot["meta"]["name"] == "process runner integration run"


def test_process_runner_records_missing_asset_database_failure(tmp_path: Path):
    result_db = tmp_path / "results.db"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(_minimal_config_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    with ProcessSimulationJobRunner(
        asset_db_path=tmp_path / "missing-assets.db",
        result_db_path=result_db,
        max_workers=1,
        job_id_factory=lambda: "job-2",
    ) as runner:
        service = SimulationTaskService(runner)
        job_id = service.submit_file(config_path)
        result = service.get_result(job_id)
        if result.state not in {
            SimulationJobState.COMPLETED,
            SimulationJobState.FAILED,
            SimulationJobState.CANCELLED,
        }:
            result = _wait_for_terminal_result(service, job_id)

    assert result.state is SimulationJobState.FAILED
    assert result.error_message is not None
    assert "asset database does not exist" in result.error_message


def _wait_for_terminal_result(
    service: SimulationTaskService,
    job_id: str,
):
    deadline = monotonic() + 10
    while True:
        result = service.get_result(job_id)
        if result.state in {
            SimulationJobState.COMPLETED,
            SimulationJobState.FAILED,
            SimulationJobState.CANCELLED,
        }:
            return result
        if monotonic() >= deadline:
            raise AssertionError(f"仿真任务未在预期时间内结束：{job_id}")
        sleep(0.01)


def _minimal_config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "simulation_config",
        "meta": {"name": "process runner integration run", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": "character:test_character",
                    "level": 90,
                    "constellation": 0,
                    "talents": {"normal_attack": 1},
                },
                "weapon": {
                    "asset_key": "weapon:test_sword",
                    "level": 90,
                    "refinement": 1,
                },
                "artifacts": {
                    "sets": [
                        {
                            "asset_key": "artifact_set:test_set",
                            "pieces": 4,
                        }
                    ],
                    "stats": {},
                },
            }
        ],
        "scene": {
            "targets": [
                {
                    "id": "target_1",
                    "level": 90,
                    "position": {"x": 0, "y": 0, "z": 0},
                    "resistance": {},
                }
            ]
        },
        "input_trace": [
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
        "rules": {"enabled": []},
        "run_options": {"max_frames": 10},
    }
