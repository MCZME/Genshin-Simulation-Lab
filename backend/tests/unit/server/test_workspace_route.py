"""workspace HTTP 路由单元测试。"""

from typing import cast

from fastapi.testclient import TestClient

from genshin_sim.application import ApplicationError, ApplicationFacade, WorkspaceInfo
from genshin_sim.server import create_app


def test_workspace_endpoint_returns_dto(application_facade) -> None:
    app = create_app(
        application_facade(workspace=WorkspaceInfo("E:/sim/data", "project-amber:1", True))
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/workspace")

    assert response.status_code == 200
    assert response.json() == {
        "initialized": True,
        "asset_db_version": "project-amber:1",
        "name": "Genshin Simulation Lab",
    }


def test_workspace_endpoint_maps_application_error() -> None:
    class _BrokenFacade:
        def get_workspace(self) -> WorkspaceInfo:
            raise ApplicationError("asset_unavailable", "asset database unavailable")

    app = create_app(cast(ApplicationFacade, _BrokenFacade()))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/workspace")

    assert response.status_code == 500
    assert response.json() == {
        "code": "asset_unavailable",
        "message": "asset database unavailable",
        "details": [],
    }


def test_workspace_endpoint_returns_uninitialized_without_data_dir(application_facade) -> None:
    app = create_app(
        application_facade(
            workspace=WorkspaceInfo("E:/sim/data", "", False),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/workspace")

    assert response.status_code == 200
    assert response.json() == {
        "initialized": False,
        "asset_db_version": "",
        "name": "Genshin Simulation Lab",
    }
