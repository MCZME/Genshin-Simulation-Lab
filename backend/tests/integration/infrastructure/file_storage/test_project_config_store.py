from __future__ import annotations

import pytest

from genshin_sim.application.config import ProjectConfig
from genshin_sim.application.errors import ConfigFileError
from genshin_sim.infrastructure.file_storage import ProjectConfigFileStore


def _write_example(tmp_path) -> None:
    (tmp_path / "config.example.toml").write_text(
        '# 项目配置\nschema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )


def test_store_create_default_and_load(tmp_path):
    store = ProjectConfigFileStore()
    _write_example(tmp_path)

    path = store.create_default(tmp_path)
    config = store.load(tmp_path)

    assert path.name == "config.toml"
    assert config.schema_version == 1
    assert config.workspace.data_dir == "data"
    assert "# 项目配置" in path.read_text(encoding="utf-8")


def test_store_save_preserves_comments_and_updates_values(tmp_path):
    store = ProjectConfigFileStore()
    _write_example(tmp_path)
    store.create_default(tmp_path)
    config = ProjectConfig.from_mapping({"schema_version": 1, "workspace": {"data_dir": "lab"}})

    store.save(tmp_path, config)

    text = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "# 项目配置" in text
    assert 'data_dir = "lab"' in text
    assert store.load(tmp_path).workspace.data_dir == "lab"


def test_store_save_creates_missing_file(tmp_path):
    store = ProjectConfigFileStore()

    store.save(tmp_path, ProjectConfig())

    assert (tmp_path / "config.toml").exists()
    assert store.load(tmp_path).workspace.data_dir == "data"


def test_store_create_default_missing_example_raises(tmp_path):
    with pytest.raises(ConfigFileError, match="缺少项目配置示例文件"):
        ProjectConfigFileStore().create_default(tmp_path)


def test_store_load_missing_file_raises(tmp_path):
    with pytest.raises(ConfigFileError, match="无法读取项目配置文件"):
        ProjectConfigFileStore().load(tmp_path / "missing")


def test_store_load_invalid_toml_raises(tmp_path):
    (tmp_path / "config.toml").write_text("schema_version = [", encoding="utf-8")

    with pytest.raises(ConfigFileError, match="不是有效 TOML"):
        ProjectConfigFileStore().load(tmp_path)


def test_store_load_template_valid(tmp_path):
    _write_example(tmp_path)

    config = ProjectConfigFileStore().load_template(tmp_path)

    assert config.schema_version == 1
    assert config.workspace.data_dir == "data"


def test_store_load_template_missing_raises(tmp_path):
    with pytest.raises(ConfigFileError, match="缺少项目配置示例文件"):
        ProjectConfigFileStore().load_template(tmp_path)


def test_store_load_template_invalid_toml_raises(tmp_path):
    (tmp_path / "config.example.toml").write_text("schema_version = [", encoding="utf-8")

    with pytest.raises(ConfigFileError, match="不是有效 TOML"):
        ProjectConfigFileStore().load_template(tmp_path)


def test_store_load_template_unsupported_schema_raises(tmp_path):
    (tmp_path / "config.example.toml").write_text(
        'schema_version = 2\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigFileError, match="项目配置示例文件无效"):
        ProjectConfigFileStore().load_template(tmp_path)


def test_store_save_persists_ui_settings_and_preserves_comments(tmp_path):
    store = ProjectConfigFileStore()
    _write_example(tmp_path)
    store.create_default(tmp_path)
    config = ProjectConfig.from_mapping(
        {"schema_version": 1, "workspace": {}, "ui": {"run_animation": False}}
    )

    store.save(tmp_path, config)

    text = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "# 项目配置" in text
    assert "run_animation = false" in text
    assert store.load(tmp_path).ui.run_animation is False


def test_store_load_older_config_without_ui_section_uses_default(tmp_path):
    store = ProjectConfigFileStore()
    (tmp_path / "config.toml").write_text(
        'schema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )

    config = store.load(tmp_path)

    assert config.ui.run_animation is True
