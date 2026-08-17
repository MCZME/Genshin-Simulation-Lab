"""application facade 单元测试。"""

from pathlib import Path
from typing import cast

import pytest

from genshin_sim.application import ApplicationFacade, AssetListKind, create_application
from genshin_sim.application.execution.models import CompletedSimulationRun, FailedSimulationRun
from genshin_sim.application.models import RecordedEvent, RunDetail, RunListItem
from tests.helpers.asset_repository import FakeAssetRepository
from tests.helpers.project import FakeProjectConfigStore


class _FakeResultRepository:
    def __init__(self, runs: tuple[RunListItem, ...] = ()) -> None:
        self.runs = runs

    def list_runs(self, limit: int = 50, state: str | None = None) -> tuple[RunListItem, ...]:
        return self.runs

    def get_run(self, session_id: str) -> RunDetail:
        raise LookupError(session_id)

    def get_events(
        self,
        session_id: str,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> tuple[RecordedEvent, ...]:
        return ()


class _FakeResultWriter:
    def save_run(self, run: CompletedSimulationRun) -> str:
        return run.session_id

    def save_failed_run(self, run: FailedSimulationRun) -> str:
        return run.session_id


def _make_facade(
    *,
    project_root: Path = Path("project"),
    asset_repository: FakeAssetRepository | None = None,
    asset_db_path: Path = Path("assets.db"),
    result_repository: _FakeResultRepository | None = None,
) -> ApplicationFacade:
    return cast(
        ApplicationFacade,
        create_application(
            project_root=project_root,
            config_store=FakeProjectConfigStore(),
            asset_repository=asset_repository
            or FakeAssetRepository(meta={"data_version": "test-1"}),
            asset_db_path=asset_db_path,
            result_repository=result_repository or _FakeResultRepository(),
            result_writer=_FakeResultWriter(),
        ),
    )


def test_default_facade_returns_initialized_workspace(monkeypatch) -> None:
    project_root = Path("project")
    config_path = project_root / "config.toml"
    asset_db_path = Path("assets.db")
    monkeypatch.setattr(Path, "is_file", lambda self: self in {config_path, asset_db_path})
    facade = _make_facade(project_root=project_root, asset_db_path=asset_db_path)

    workspace = facade.get_workspace()

    assert workspace.data_dir == str(project_root / "data")
    assert workspace.asset_db_version == "test-1"
    assert workspace.initialized is True


@pytest.mark.parametrize(
    ("existing_paths", "asset_db_path"),
    [
        pytest.param(("assets.db",), "assets.db", id="missing-config"),
        pytest.param(("project/config.toml",), "missing.db", id="missing-asset-db"),
    ],
)
def test_default_facade_returns_uninitialized_workspace(
    monkeypatch,
    existing_paths: tuple[str, ...],
    asset_db_path: str,
) -> None:
    project_root = Path("project")
    existing = {Path(path) for path in existing_paths}
    monkeypatch.setattr(Path, "is_file", lambda self: self in existing)
    facade = _make_facade(project_root=project_root, asset_db_path=Path(asset_db_path))

    workspace = facade.get_workspace()

    assert workspace.data_dir == str(project_root / "data")
    assert workspace.asset_db_version == ""
    assert workspace.initialized is False


def test_facade_lists_assets() -> None:
    facade = _make_facade(asset_repository=FakeAssetRepository(meta={"data_version": "test-1"}))

    assets = facade.list_assets(AssetListKind.CHARACTERS)

    assert len(assets) == 1
    assert assets[0].asset_key == "character:75"
    assert assets[0].name == "test"


def test_facade_lists_results() -> None:
    run = RunListItem(
        session_id="session-1",
        state="completed",
        name="demo",
        stop_reason="script_end",
        end_frame=10,
        frames_run=10,
        created_at="2026-01-01T00:00:00+00:00",
        event_count=2,
    )
    facade = _make_facade(result_repository=_FakeResultRepository((run,)))

    result = facade.list_results()

    assert result == (run,)
