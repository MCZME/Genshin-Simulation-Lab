from __future__ import annotations

import json
import logging
from pathlib import Path

from genshin_sim.cli.main import main
from genshin_sim.infrastructure.assets_sqlite import write_minimal_static_asset_database
from genshin_sim.infrastructure.results_sqlite import SQLiteResultRepository


def test_cli_run_persists_minimal_input_to_result_database(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    asset_db = tmp_path / "assets.db"
    result_db = tmp_path / "results.db"
    input_path = tmp_path / "config.json"
    (tmp_path / "config.toml").write_text(
        'schema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    write_minimal_static_asset_database(asset_db)
    input_path.write_text(
        json.dumps(_minimal_input_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    executor_logger = logging.getLogger("genshin_sim.application.execution.executor")
    previous_level = executor_logger.level
    recorder = _RecordHandler()
    executor_logger.setLevel(logging.INFO)
    executor_logger.addHandler(recorder)
    try:
        exit_code = main(
            [
                "run",
                str(input_path),
                "--db",
                str(asset_db),
                "--results-db",
                str(result_db),
            ]
        )
    finally:
        executor_logger.setLevel(previous_level)
        executor_logger.removeHandler(recorder)

    assert exit_code == 0
    output = capsys.readouterr().out
    session_id = _extract_session_id(output)
    key_messages = {"仿真组装开始", "仿真运行开始", "仿真运行完成", "仿真结果已保存"}
    key_records = [record for record in recorder.records if record.getMessage() in key_messages]
    assert {getattr(record, "session_id", "") for record in key_records} == {session_id}
    detail = SQLiteResultRepository(result_db).get_run(session_id)
    assert detail.state == "completed"
    assert detail.initial_snapshot is not None
    assert {"space", "aura", "aura_icd", "team"} <= set(detail.initial_snapshot["providers"])
    event_types = [event.event_type for event in detail.events]

    assert detail.summary is not None
    assert detail.summary.stop_reason == "COMPLETED"
    assert detail.summary.end_frame == 3
    assert event_types == [
        "SIMULATION_STARTED",
        "RESONANCE_ACTIVATED",
        "INPUT_KEY_RECEIVED",
        "INPUT_SESSION_BOUNDARY_REACHED",
        "MOONSIGN_LEVEL_SET",
        "INPUT_KEY_RECEIVED",
        "INPUT_SESSION_BOUNDARY_REACHED",
        "ACTION_STARTED",
        "AURA_ICD_RESOLVED",
        "AURA_APPLIED",
        "DAMAGE_RESOLVED",
        "ELEMENTAL_INTERACTION_RESOLVED",
        "SIMULATION_ENDED",
    ]
    assert detail.events[1].data == {
        "active_keys": [],
        "team_size": 1,
        "established_frame": 0,
    }
    assert detail.events[2].data == {
        "key": "keyboard.e",
        "phase": "press",
        "order": 0,
        "session_id": 1,
    }
    assert detail.events[3].data["will_interpret"] is True
    assert detail.events[5].data == {
        "key": "keyboard.e",
        "phase": "release",
        "order": 0,
        "session_id": 1,
    }
    assert detail.events[6].data["held_frames"] == 1
    assert detail.events[7].data["action_key"] == "character.testing.runtime_probe.action"
    assert detail.events[10].data["result"]["final_damage"] > 0
    assert detail.events[12].data == {
        "stop_reason": "COMPLETED",
        "end_frame": 3,
        "frames_run": 3,
    }
    assert detail.input_snapshot["team"][0]["character"]["asset_key"] == (
        "character:test_character"
    )


def _extract_session_id(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("session_id: "):
            return line.removeprefix("session_id: ").strip()
    raise AssertionError(f"session id not found in output: {output}")


def _minimal_input_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": "minimal integration run", "description": ""},
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


class _RecordHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
