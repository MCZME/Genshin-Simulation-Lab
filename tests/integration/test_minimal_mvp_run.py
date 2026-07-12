from __future__ import annotations

import json
from pathlib import Path

from genshin_sim.cli.main import main
from genshin_sim.infrastructure.assets_sqlite import write_minimal_static_asset_database
from genshin_sim.infrastructure.results_sqlite import SQLiteResultRepository


def test_cli_run_persists_minimal_config_to_result_database(
    tmp_path: Path,
    capsys,
):
    asset_db = tmp_path / "assets.db"
    result_db = tmp_path / "results.db"
    config_path = tmp_path / "config.json"
    write_minimal_static_asset_database(asset_db)
    config_path.write_text(
        json.dumps(_minimal_config_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            str(config_path),
            "--db",
            str(asset_db),
            "--results-db",
            str(result_db),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    session_id = _extract_session_id(output)
    detail = SQLiteResultRepository(result_db).get_run(session_id)
    event_types = [event.event_type for event in detail.events]

    assert detail.summary.stop_reason == "COMPLETED"
    assert detail.summary.end_frame == 3
    assert event_types == [
        "SIMULATION_STARTED",
        "INPUT_KEY_RECEIVED",
        "INPUT_SESSION_BOUNDARY_REACHED",
        "INPUT_KEY_RECEIVED",
        "INPUT_SESSION_BOUNDARY_REACHED",
        "DAMAGE_RESOLVED",
        "SIMULATION_ENDED",
    ]
    assert detail.events[1].data == {
        "key": "keyboard.e",
        "phase": "press",
        "order": 0,
        "session_id": 1,
    }
    assert detail.events[2].data["will_interpret"] is True
    assert detail.events[3].data == {
        "key": "keyboard.e",
        "phase": "release",
        "order": 0,
        "session_id": 1,
    }
    assert detail.events[4].data["held_frames"] == 1
    assert detail.events[5].data["result"]["final_damage"] > 0
    assert detail.events[6].data == {
        "stop_reason": "COMPLETED",
        "end_frame": 3,
        "frames_run": 3,
    }
    assert detail.config_snapshot["team"][0]["character"]["asset_key"] == (
        "character:test_character"
    )


def _extract_session_id(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("session_id: "):
            return line.removeprefix("session_id: ").strip()
    raise AssertionError(f"session id not found in output: {output}")


def _minimal_config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "simulation_config",
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
