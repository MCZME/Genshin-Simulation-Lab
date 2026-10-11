"""server app factory 单元测试。"""

import pytest
from fastapi.testclient import TestClient

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
        "/api/v1/analysis/schema": {"get"},
        "/api/v1/analysis/runtime/contexts": {"post"},
        "/api/v1/analysis/runtime/contexts/{context_id}": {"delete"},
        "/api/v1/analysis/runtime/contexts/{context_id}/nodes/execute": {"post"},
        "/api/v1/analysis/runtime/contexts/{context_id}/stages/{stage_id}": {"get"},
        "/api/v1/analysis/runtime/contexts/{context_id}/stages/{stage_id}/select": {"post"},
        "/api/v1/analysis/runtime/contexts/{context_id}/merge": {"post"},
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
        "/api/v1/results/{session_id}/events/{ordinal}": {"get"},
        "/api/v1/results/{session_id}/frames/{frame}": {"get"},
        "/api/v1/assets/{asset_type}": {"get"},
        "/api/v1/assets/{asset_type}/{source_id}": {"get"},
        "/api/v1/assets/resolve": {"post"},
    }
    methods = {
        (path, method)
        for path, operations in schema["paths"].items()
        for method in operations
        if method in {"get", "post", "put", "delete"}
    }

    assert methods == {(path, method) for path, allowed in expected.items() for method in allowed}


def test_create_app_serves_frontend_static_dir(application_facade, tmp_path) -> None:
    static_dir = tmp_path / "dist"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "index.html").write_text("<html>frontend</html>", encoding="utf-8")
    (static_dir / "assets" / "app.js").write_text("export {}", encoding="utf-8")

    app = create_app(
        application_facade(workspace=WorkspaceInfo("data", "v1", True)),
        static_dir=static_dir,
    )

    with TestClient(app) as client:
        index_response = client.get("/")
        asset_response = client.get("/assets/app.js")
        api_miss_response = client.get("/api/v1/nonexistent")

    assert index_response.status_code == 200
    assert index_response.text == "<html>frontend</html>"
    # 入口页不带内容 hash，必须强制重验证，避免重建后浏览器使用旧页面
    assert index_response.headers["cache-control"] == "no-cache"
    assert asset_response.status_code == 200
    assert asset_response.text == "export {}"
    assert asset_response.headers["cache-control"] == "public, max-age=31536000, immutable"
    # 未命中的 API 路径不被静态托管吞掉，仍返回 404
    assert api_miss_response.status_code == 404


def test_create_app_rejects_invalid_static_dir(application_facade, tmp_path) -> None:
    with pytest.raises(RuntimeError, match="index.html"):
        create_app(
            application_facade(workspace=WorkspaceInfo("data", "v1", True)),
            static_dir=tmp_path / "missing",
        )
