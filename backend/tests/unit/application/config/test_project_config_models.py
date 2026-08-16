from __future__ import annotations

from pathlib import Path

import pytest

from genshin_sim.application.config import (
    PROJECT_CONFIG_SCHEMA_VERSION,
    ConfigError,
    ProjectConfig,
)


def test_project_config_defaults():
    config = ProjectConfig()

    assert config.schema_version == PROJECT_CONFIG_SCHEMA_VERSION
    assert config.workspace.data_dir == "data"
    assert config.to_dict() == {"schema_version": 1, "workspace": {"data_dir": "data"}}


def test_project_config_from_mapping():
    config = ProjectConfig.from_mapping({"schema_version": 1, "workspace": {"data_dir": "lab"}})

    assert config.workspace.data_dir == "lab"


def test_project_config_rejects_unsupported_schema_version():
    with pytest.raises(ConfigError, match="不支持的 schema_version"):
        ProjectConfig.from_mapping({"schema_version": 2, "workspace": {}})


def test_project_config_rejects_empty_data_dir():
    with pytest.raises(ConfigError, match="workspace.data_dir 必须是非空字符串"):
        ProjectConfig.from_mapping({"schema_version": 1, "workspace": {"data_dir": ""}})


def test_workspace_paths_resolve_relative_to_project_root(tmp_path):
    config = ProjectConfig()

    assert config.data_dir(tmp_path) == tmp_path / "data"
    assert config.inputs_dir(tmp_path) == tmp_path / "data" / "inputs"
    assert config.results_dir(tmp_path) == tmp_path / "data" / "results"
    assert config.results_db(tmp_path) == tmp_path / "data" / "results" / "results.db"
    assert config.logs_dir(tmp_path) == tmp_path / "data" / "logs"
    assert config.exports_dir(tmp_path) == tmp_path / "data" / "exports"
    assert config.templates_dir(tmp_path) == tmp_path / "data" / "templates"


def test_workspace_paths_accept_absolute_data_dir():
    config = ProjectConfig.from_mapping(
        {"schema_version": 1, "workspace": {"data_dir": "/abs/lab"}}
    )

    assert config.data_dir("/unrelated") == Path("/abs/lab")
    assert config.inputs_dir("/unrelated") == Path("/abs/lab") / "inputs"
    assert config.logs_dir("/unrelated") == Path("/abs/lab") / "logs"
