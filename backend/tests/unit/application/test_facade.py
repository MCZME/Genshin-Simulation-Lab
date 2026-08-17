"""application facade 单元测试。"""

from pathlib import Path

from genshin_sim.application.facade import DefaultApplicationFacade
from tests.helpers.asset_repository import FakeAssetRepository
from tests.helpers.project import FakeProjectConfigStore


def test_default_facade_returns_initialized_workspace(monkeypatch) -> None:
    project_root = Path("project")
    config_path = project_root / "config.toml"
    asset_db_path = Path("assets.db")
    monkeypatch.setattr(Path, "is_file", lambda self: self in {config_path, asset_db_path})
    facade = DefaultApplicationFacade(
        project_root=project_root,
        config_store=FakeProjectConfigStore(),
        asset_repository=FakeAssetRepository(meta={"data_version": "test-1"}),
        asset_db_path=asset_db_path,
    )

    workspace = facade.get_workspace()

    assert workspace.data_dir == str(project_root / "data")
    assert workspace.asset_db_version == "test-1"
    assert workspace.initialized is True


def test_default_facade_returns_uninitialized_without_config(monkeypatch) -> None:
    project_root = Path("project")
    asset_db_path = Path("assets.db")
    monkeypatch.setattr(Path, "is_file", lambda self: self == asset_db_path)
    facade = DefaultApplicationFacade(
        project_root=project_root,
        config_store=FakeProjectConfigStore(),
        asset_repository=FakeAssetRepository(),
        asset_db_path=asset_db_path,
    )

    workspace = facade.get_workspace()

    assert workspace.data_dir == str(project_root / "data")
    assert workspace.asset_db_version == ""
    assert workspace.initialized is False


def test_default_facade_returns_uninitialized_without_asset_db(monkeypatch) -> None:
    project_root = Path("project")
    config_path = project_root / "config.toml"
    monkeypatch.setattr(Path, "is_file", lambda self: self == config_path)
    facade = DefaultApplicationFacade(
        project_root=project_root,
        config_store=FakeProjectConfigStore(),
        asset_repository=FakeAssetRepository(),
        asset_db_path=Path("missing.db"),
    )

    workspace = facade.get_workspace()

    assert workspace.data_dir == str(project_root / "data")
    assert workspace.asset_db_version == ""
    assert workspace.initialized is False
