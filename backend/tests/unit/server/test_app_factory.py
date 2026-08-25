"""server app factory 单元测试。"""

from genshin_sim.application import WorkspaceInfo
from genshin_sim.server import create_app


def test_create_app_holds_injected_application(application_facade) -> None:
    application = application_facade(workspace=WorkspaceInfo("data", "v1", True))

    app = create_app(application)

    assert app.title == "Genshin Simulation Lab"
    assert app.state.application is application


def test_create_app_returns_independent_instances(application_facade) -> None:
    application = application_facade(workspace=WorkspaceInfo("data", "v1", True))

    first = create_app(application)
    second = create_app(application)

    assert first is not second


def test_openapi_exposes_all_mvp_endpoints(application_facade) -> None:
    app = create_app(application_facade(workspace=WorkspaceInfo("data", "v1", True)))
    schema = app.openapi()

    expected = {
        "/api/v1/analysis/query": {"post"},
        "/api/v1/analysis/schema": {"get"},
        "/api/v1/workspace": {"get"},
        "/api/v1/settings": {"get", "put"},
        "/api/v1/workflows": {"get", "post"},
        "/api/v1/workflows/{workflow_id}": {"get", "put", "delete"},
        "/api/v1/inputs/validate": {"post"},
        "/api/v1/runs": {"post"},
        "/api/v1/runs/{run_id}": {"get"},
        "/api/v1/runs/{run_id}/cancel": {"post"},
        "/api/v1/results": {"get"},
        "/api/v1/results/{session_id}": {"get"},
        "/api/v1/results/{session_id}/events": {"get"},
        "/api/v1/assets/{asset_type}": {"get"},
        "/api/v1/assets/{asset_type}/{source_id}": {"get"},
    }
    methods = {
        (path, method)
        for path, operations in schema["paths"].items()
        for method in operations
        if method in {"get", "post", "put", "delete"}
    }

    assert methods == {(path, method) for path, allowed in expected.items() for method in allowed}
