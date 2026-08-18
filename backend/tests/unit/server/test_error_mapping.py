"""HTTP 统一错误映射单元测试。"""

from typing import cast

from fastapi.testclient import TestClient

from genshin_sim.application import ApplicationError, ApplicationFacade, WorkflowSummary
from genshin_sim.server import create_app


def _app_raising(code: str) -> TestClient:
    class _BrokenFacade:
        def get_workspace(self):
            from genshin_sim.application import WorkspaceInfo

            return WorkspaceInfo("data", "v1", True)

        def list_workflows(self) -> tuple[WorkflowSummary, ...]:
            raise ApplicationError(code, f"message for {code}", ({"key": "value"},))

    app = create_app(cast(ApplicationFacade, _BrokenFacade()))
    return TestClient(app, raise_server_exceptions=False)


def test_not_found_error_maps_to_404() -> None:
    with _app_raising("not_found") as client:
        response = client.get("/api/v1/workflows")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_validation_error_maps_to_400() -> None:
    with _app_raising("validation_failed") as client:
        response = client.get("/api/v1/workflows")

    assert response.status_code == 400
    assert response.json()["details"] == [{"key": "value"}]


def test_conflict_error_maps_to_409() -> None:
    with _app_raising("metrics_unavailable") as client:
        response = client.get("/api/v1/workflows")

    assert response.status_code == 409


def test_unknown_application_error_maps_to_500() -> None:
    with _app_raising("mystery_code") as client:
        response = client.get("/api/v1/workflows")

    assert response.status_code == 500
    assert response.json()["code"] == "mystery_code"
