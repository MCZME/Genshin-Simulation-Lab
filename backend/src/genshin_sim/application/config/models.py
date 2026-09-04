from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from genshin_sim.application.errors import ConfigError
from genshin_sim.application.validation import _require_int, _require_mapping, _require_string

PROJECT_CONFIG_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class WorkspaceConfig:
    """项目工作区配置。"""

    data_dir: str = "data"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> WorkspaceConfig:
        data_dir = _require_string(raw.get("data_dir", "data"), "workspace.data_dir")
        return cls(data_dir=data_dir)

    def to_dict(self) -> dict[str, Any]:
        return {"data_dir": self.data_dir}


@dataclass(frozen=True, slots=True)
class UiConfig:
    """界面偏好设置；语义由前端定义，此处只做类型与取值校验。"""

    run_animation: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> UiConfig:
        value = raw.get("run_animation", True)
        if not isinstance(value, bool):
            raise ConfigError("ui.run_animation 必须是布尔值")
        return cls(run_animation=value)

    def to_dict(self) -> dict[str, Any]:
        return {"run_animation": self.run_animation}


@dataclass(frozen=True, slots=True)
class DeveloperConfig:
    """开发者模式配置；开启后注册并可见 content/test 测试内容。"""

    enabled: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> DeveloperConfig:
        value = raw.get("enabled", False)
        if not isinstance(value, bool):
            raise ConfigError("developer.enabled 必须是布尔值")
        return cls(enabled=value)

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled}


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """项目配置（config.toml）。"""

    schema_version: int = PROJECT_CONFIG_SCHEMA_VERSION
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    developer: DeveloperConfig = field(default_factory=DeveloperConfig)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> ProjectConfig:
        schema_version = _require_int(raw.get("schema_version"), "schema_version")
        if schema_version != PROJECT_CONFIG_SCHEMA_VERSION:
            raise ConfigError(f"不支持的 schema_version：{schema_version}")
        return cls(
            schema_version=schema_version,
            workspace=WorkspaceConfig.from_mapping(
                _require_mapping(raw.get("workspace", {}), "workspace")
            ),
            ui=UiConfig.from_mapping(_require_mapping(raw.get("ui", {}), "ui")),
            developer=DeveloperConfig.from_mapping(
                _require_mapping(raw.get("developer", {}), "developer")
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workspace": self.workspace.to_dict(),
            "ui": self.ui.to_dict(),
            "developer": self.developer.to_dict(),
        }

    def _data_dir_path(self, project_root: str | Path) -> Path:
        data_dir = Path(self.workspace.data_dir)
        if data_dir.is_absolute():
            return data_dir
        return Path(project_root) / data_dir

    def data_dir(self, project_root: str | Path) -> Path:
        return self._data_dir_path(project_root)

    def inputs_dir(self, project_root: str | Path) -> Path:
        return self._data_dir_path(project_root) / "inputs"

    def results_dir(self, project_root: str | Path) -> Path:
        return self._data_dir_path(project_root) / "results"

    def results_db(self, project_root: str | Path) -> Path:
        return self.results_dir(project_root) / "results.db"

    def logs_dir(self, project_root: str | Path) -> Path:
        return self._data_dir_path(project_root) / "logs"

    def exports_dir(self, project_root: str | Path) -> Path:
        return self._data_dir_path(project_root) / "exports"

    def templates_dir(self, project_root: str | Path) -> Path:
        return self._data_dir_path(project_root) / "templates"
