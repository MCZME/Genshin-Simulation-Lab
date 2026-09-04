"""进程仿真任务 runner（ProcessSimulationJobRunner）的纵向集成。"""

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
from genshin_sim.infrastructure.jobs import ProcessSimulationJobRunner
from genshin_sim.infrastructure.results_sqlite import SQLiteResultRepository
from tests.helpers.assembly import static_asset_input_payload
from tests.helpers.fixture_assets import write_fixture_asset_database


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
    write_fixture_asset_database(asset_db)
    input_path.write_text(
        json.dumps(
            static_asset_input_payload(
                meta_name="process runner integration run",
                include_weapon=True,
                include_artifact_set=True,
                input_trace=[],
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with ProcessSimulationJobRunner(
        asset_db_path=asset_db,
        result_db_path=result_db,
        max_workers=1,
        developer_mode=False,
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
        json.dumps(
            static_asset_input_payload(
                meta_name="process runner integration run",
                include_weapon=True,
                include_artifact_set=True,
            ),
            ensure_ascii=False,
        ),
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
