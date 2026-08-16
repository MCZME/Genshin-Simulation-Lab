"""项目配置（config.toml）的文件存储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.exceptions import ParseError

from genshin_sim.application.config import ProjectConfig
from genshin_sim.application.errors import ConfigError, ConfigFileError

CONFIG_FILE_NAME = "config.toml"
EXAMPLE_FILE_NAME = "config.example.toml"


class ProjectConfigFileStore:
    """基于 config.toml 的项目配置读写，写入时保留用户注释。"""

    def __init__(
        self,
        file_name: str = CONFIG_FILE_NAME,
        example_file_name: str = EXAMPLE_FILE_NAME,
    ) -> None:
        self.file_name = file_name
        self.example_file_name = example_file_name

    def config_path(self, project_root: str | Path) -> Path:
        return Path(project_root) / self.file_name

    def template_path(self, project_root: str | Path) -> Path:
        return Path(project_root) / self.example_file_name

    def load(self, project_root: str | Path) -> ProjectConfig:
        path = self.config_path(project_root)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigFileError(f"无法读取项目配置文件：{path}") from exc
        try:
            document = tomlkit.parse(text)
        except ParseError as exc:
            raise ConfigFileError(f"项目配置文件不是有效 TOML：{path}") from exc
        return ProjectConfig.from_mapping(_document_to_mapping(document))

    def load_template(self, project_root: str | Path) -> ProjectConfig:
        path = self.template_path(project_root)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigFileError(f"缺少项目配置示例文件：{path}") from exc
        try:
            document = tomlkit.parse(text)
        except ParseError as exc:
            raise ConfigFileError(f"项目配置示例文件不是有效 TOML：{path}") from exc
        try:
            return ProjectConfig.from_mapping(_document_to_mapping(document))
        except ConfigError as exc:
            raise ConfigFileError(f"项目配置示例文件无效：{path}：{exc}") from exc

    def save(self, project_root: str | Path, config: ProjectConfig) -> Path:
        path = self.config_path(project_root)
        if path.exists():
            try:
                document = tomlkit.parse(path.read_text(encoding="utf-8"))
            except OSError as exc:
                raise ConfigFileError(f"无法读取项目配置文件：{path}") from exc
            except ParseError as exc:
                raise ConfigFileError(f"项目配置文件不是有效 TOML：{path}") from exc
        else:
            document = tomlkit.document()

        document["schema_version"] = config.schema_version
        if "workspace" not in document:
            document["workspace"] = tomlkit.table()
        workspace = document["workspace"]
        workspace["data_dir"] = config.workspace.data_dir

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomlkit.dumps(document), encoding="utf-8")
        return path

    def create_default(self, project_root: str | Path) -> Path:
        example_path = Path(project_root) / self.example_file_name
        try:
            content = example_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigFileError(f"缺少项目配置示例文件：{example_path}") from exc
        path = self.config_path(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


def _document_to_mapping(document: Any) -> dict[str, Any]:
    """把 tomlkit 文档转成普通 dict，保留嵌套 workspace 为 mapping。"""

    return dict(document)
