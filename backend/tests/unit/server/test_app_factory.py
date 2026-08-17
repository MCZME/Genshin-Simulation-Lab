"""server app factory 单元测试。"""

from fastapi.testclient import TestClient

from genshin_sim.application import WorkspaceInfo
from genshin_sim.application.errors import ApplicationError
from genshin_sim.server import create_app


class _FakeFacade:
    def __init__(self, workspace: WorkspaceInfo) -> None:
        self._workspace = workspace

    def get_workspace(self) -> WorkspaceInfo:
        return self._workspace


def test_create_app_holds_injected_application() -> None:
    application = _FakeFacade(WorkspaceInfo("data", "v1", True))

    app = create_app(application)

    assert app.title == "Genshin Simulation Lab"
    assert app.state.application is application


def test_create_app_returns_independent_instances() -> None:
    application = _FakeFacade(WorkspaceInfo("data", "v1", True))

    first = create_app(application)
    second = create_app(application)

    assert first is not second


def test_workspace_endpoint_returns_dto() -> None:
    application = _FakeFacade(WorkspaceInfo("E:/sim/data", "project-amber:1", True))

    app = create_app(application)
    with TestClient(app) as client:
        response = client.get("/api/v1/workspace")

    assert response.status_code == 200
    assert response.json() == {
        "data_dir": "E:/sim/data",
        "asset_db_version": "project-amber:1",
        "initialized": True,
    }


def test_workspace_endpoint_maps_application_error() -> None:
    class BrokenFacade:
        def get_workspace(self) -> WorkspaceInfo:
            raise ApplicationError("asset_unavailable", "asset database unavailable")

    app = create_app(BrokenFacade())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/workspace")

    assert response.status_code == 500
    assert response.json() == {
        "code": "asset_unavailable",
        "message": "asset database unavailable",
        "details": [],
    }
