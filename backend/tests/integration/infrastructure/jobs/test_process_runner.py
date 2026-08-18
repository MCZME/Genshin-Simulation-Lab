from __future__ import annotations

import json
from pathlib import Path

from genshin_sim.application import BatchMember
from genshin_sim.application.batch import (
    BatchRunService,
    BatchValidationResult,
)
from genshin_sim.application.batch.models import BatchMemberValidation
from genshin_sim.application.input import SimulationInput
from genshin_sim.infrastructure.assets_sqlite import write_minimal_static_asset_database
from genshin_sim.infrastructure.jobs import ProcessSimulationJobRunner
from genshin_sim.infrastructure.results_sqlite import SQLiteResultRepository


class _PassthroughValidator:
    def validate_members(self, members) -> BatchValidationResult:
        return BatchValidationResult(
            ok=True,
            members=tuple(
                BatchMemberValidation(item_id=member.item_id, ok=True) for member in members
            ),
            normalized_members=tuple(members),
        )


def test_process_runner_runs_file_and_persists_result(tmp_path: Path):
    asset_db = tmp_path / "assets.db"
    result_db = tmp_path / "results.db"
    input_path = tmp_path / "config.json"
    write_minimal_static_asset_database(asset_db)
    input_path.write_text(
        json.dumps(_minimal_input_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    with ProcessSimulationJobRunner(
        asset_db_path=asset_db,
        result_db_path=result_db,
        max_workers=1,
        job_id_factory=lambda: "job-1",
    ) as runner:
        service = BatchRunService(
            runner,
            validator=_PassthroughValidator(),
            run_id_factory=lambda: "run-1",
        )

        result = service.run_single_and_wait(
            BatchMember(
                item_id="item-1",
                input=SimulationInput.from_json_file(input_path),
            ),
            poll_interval_seconds=0.01,
            timeout_seconds=10,
        )

    assert result.session_id is not None
    assert result.error_code is None

    detail = SQLiteResultRepository(result_db).get_run(result.session_id)
    assert detail.summary is not None
    assert detail.summary.stop_reason == "COMPLETED"
    assert detail.input_snapshot["meta"]["name"] == "process runner integration run"


def test_process_runner_records_missing_asset_database_failure(tmp_path: Path):
    result_db = tmp_path / "results.db"
    input_path = tmp_path / "config.json"
    input_path.write_text(
        json.dumps(_minimal_input_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    with ProcessSimulationJobRunner(
        asset_db_path=tmp_path / "missing-assets.db",
        result_db_path=result_db,
        max_workers=1,
        job_id_factory=lambda: "job-2",
    ) as runner:
        service = BatchRunService(
            runner,
            validator=_PassthroughValidator(),
            run_id_factory=lambda: "run-2",
        )
        result = service.run_single_and_wait(
            BatchMember(
                item_id="item-2",
                input=SimulationInput.from_json_file(input_path),
            ),
            poll_interval_seconds=0.01,
            timeout_seconds=10,
        )

    assert result.error_message is not None
    assert "asset database does not exist" in result.error_message


def _minimal_input_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "kind": "simulation_input",
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
