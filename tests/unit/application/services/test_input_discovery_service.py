from __future__ import annotations

import json
from pathlib import Path

from genshin_sim.application.services import InputDiscoveryService
from tests.helpers.project import FakeProjectConfigStore


def _write_input(
    project_root: Path,
    data_dir: str,
    name: str,
    *,
    valid: bool = True,
) -> Path:
    inputs_dir = project_root / data_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    path = inputs_dir / f"{name}.json"
    if valid:
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "kind": "simulation_input",
                    "meta": {"name": name, "description": ""},
                    "team": [],
                    "scene": {"player": {}, "targets": []},
                    "input_trace": [],
                    "rules": {"enabled": []},
                    "run_options": {"max_frames": 10},
                }
            ),
            encoding="utf-8",
        )
    else:
        path.write_text("{invalid", encoding="utf-8")
    return path


def test_list_inputs_returns_empty_when_inputs_dir_missing(tmp_path):
    service = InputDiscoveryService(FakeProjectConfigStore())

    assert service.list_inputs(tmp_path) == ()


def test_list_inputs_scans_valid_and_invalid_files(tmp_path):
    service = InputDiscoveryService(FakeProjectConfigStore())
    valid_path = _write_input(tmp_path, "data", "rotation_a")
    _write_input(tmp_path, "data", "broken", valid=False)

    items = service.list_inputs(tmp_path)

    assert [item.input_key for item in items] == ["broken", "rotation_a"]
    broken, valid = items
    assert broken.error is not None
    assert valid.path == valid_path
    assert valid.name == "rotation_a"
    assert valid.schema_version == 2
    assert valid.error is None


def test_list_inputs_uses_configured_data_dir(tmp_path):
    service = InputDiscoveryService(FakeProjectConfigStore(data_dir="lab"))
    _write_input(tmp_path, "lab", "rotation_b")

    items = service.list_inputs(tmp_path)

    assert [item.input_key for item in items] == ["rotation_b"]
