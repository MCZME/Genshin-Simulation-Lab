from __future__ import annotations

from pathlib import Path

from genshin_sim.application.config import ProjectConfig


class FakeProjectConfigStore:
    """项目配置存储协议的内存假实现，供服务层测试复用。"""

    def __init__(self, data_dir: str = "data") -> None:
        self.data_dir = data_dir
        self.created: Path | None = None

    def config_path(self, project_root: str | Path) -> Path:
        return Path(project_root) / "config.toml"

    def template_path(self, project_root: str | Path) -> Path:
        return Path(project_root) / "config.example.toml"

    def load(self, project_root: str | Path) -> ProjectConfig:
        return ProjectConfig.from_mapping(
            {"schema_version": 1, "workspace": {"data_dir": self.data_dir}}
        )

    def load_template(self, project_root: str | Path) -> ProjectConfig:
        return self.load(project_root)

    def save(self, project_root: str | Path, config: ProjectConfig) -> Path:
        return Path(project_root) / "config.toml"

    def create_default(self, project_root: str | Path) -> Path:
        self.created = Path(project_root) / "config.toml"
        return self.created
