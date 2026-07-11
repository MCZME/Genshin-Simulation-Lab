from __future__ import annotations

import json
from pathlib import Path

import pytest

from genshin_sim.application.config import (
    ConfigError,
    InputFrameConfig,
    KeyEventConfig,
    SimulationConfig,
    load_simulation_config,
)


def _minimal_config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "simulation_config",
        "meta": {"name": "demo", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": "character:75",
                    "level": 90,
                    "constellation": 2,
                    "talents": {
                        "normal_attack": 1,
                        "elemental_skill": 10,
                        "elemental_burst": 10,
                    },
                },
                "weapon": {
                    "asset_key": "weapon:11512",
                    "level": 90,
                    "refinement": 1,
                },
                "artifacts": {
                    "sets": [
                        {
                            "asset_key": "artifact_set:15032",
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
            {
                "frame": 1,
                "events": [
                    {"key": "keyboard.e", "phase": "press"},
                ],
            },
            {
                "frame": 2,
                "events": [
                    {"key": "keyboard.e", "phase": "release"},
                ],
            },
        ],
        "rules": {"enabled": []},
        "run_options": {"max_frames": 18000},
    }


def test_simulation_config_round_trips_to_dict():
    config = SimulationConfig.from_mapping(_minimal_config_payload())

    assert config.schema_version == 1
    assert config.kind == "simulation_config"
    assert config.team[0].character.asset_key == "character:75"
    assert config.scene.player.position.x == 0
    assert config.scene.player.facing.z == 1
    assert config.scene.targets[0].target_id == "target_1"
    assert config.input_trace[0].events[0].phase.value == "press"
    assert config.to_dict()["meta"]["name"] == "demo"
    assert config.to_dict()["scene"]["player"]["facing"]["z"] == 1


def test_simulation_config_accepts_scene_player_start():
    payload = _minimal_config_payload()
    payload["scene"] = {
        "player": {
            "position": {"x": 1, "y": 2, "z": 3},
            "facing": {"x": 1, "y": 0, "z": 0},
        },
        "targets": [
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 5},
                "resistance": {},
            }
        ],
    }

    config = SimulationConfig.from_mapping(payload)

    assert config.scene.player.position.x == 1
    assert config.scene.player.position.y == 2
    assert config.scene.player.position.z == 3
    assert config.scene.player.facing.x == 1


def test_simulation_config_rejects_zero_xz_player_facing():
    payload = _minimal_config_payload()
    payload["scene"] = {
        "player": {"facing": {"x": 0, "y": 1, "z": 0}},
        "targets": [],
    }

    with pytest.raises(ConfigError, match="scene\\.player\\.facing"):
        SimulationConfig.from_mapping(payload)


def test_simulation_config_rejects_invalid_team_key():
    payload = _minimal_config_payload()
    payload["team"] = [
        {
            "slot": 1,
            "character": {
                "asset_key": "wrong:75",
                "level": 90,
            },
        }
    ]

    with pytest.raises(ConfigError, match="team\\[0\\]\\.character\\.asset_key"):
        SimulationConfig.from_mapping(payload)


def test_simulation_config_rejects_invalid_scene_target_id():
    payload = _minimal_config_payload()
    payload["scene"] = {"targets": [{"id": "", "position": {}, "resistance": {}}]}

    with pytest.raises(ConfigError, match="scene\\.targets\\[0\\]\\.id"):
        SimulationConfig.from_mapping(payload)


def test_simulation_config_rejects_unbalanced_input_trace():
    payload = _minimal_config_payload()
    payload["input_trace"] = [{"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]}]

    with pytest.raises(ConfigError, match="输入轨迹结束时仍有按键未释放"):
        SimulationConfig.from_mapping(payload)


def test_simulation_config_json_file_round_trip(tmp_path: Path):
    payload = _minimal_config_payload()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    config = load_simulation_config(path)

    assert config.to_dict()["scene"]["targets"][0]["id"] == "target_1"


def test_key_event_config_from_mapping_rejects_unknown_key():
    with pytest.raises(ConfigError, match="不支持的输入按键：keyboard.w"):
        KeyEventConfig.from_mapping(
            {"key": "keyboard.w", "phase": "press"},
            "input_trace[0].events[0]",
        )


def test_input_frame_config_to_core():
    frame = InputFrameConfig.from_mapping(
        {
            "frame": 3,
            "events": [
                {"key": "keyboard.1", "phase": "press"},
            ],
        },
        "input_trace[0]",
    )

    assert frame.to_core().frame == 3
