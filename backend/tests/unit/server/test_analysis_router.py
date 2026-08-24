"""分析模板 HTTP 路由单元测试。"""

from fastapi.testclient import TestClient

from genshin_sim.application import (
    TemplateColumn,
    TemplateDeclaration,
    TemplateOutput,
    TemplateParam,
    TemplateResult,
)
from genshin_sim.server import create_app


def _declaration() -> TemplateDeclaration:
    return TemplateDeclaration(
        template_id="session_metrics",
        display_name="每会话指标",
        params=(TemplateParam("session_ids", "string[]", True, ("session_group",)),),
        relations=(),
        output=TemplateOutput(columns=(TemplateColumn("session_id", "string"),)),
    )


def test_analysis_templates_list(application_facade) -> None:
    app = create_app(application_facade(analysis_declarations=(_declaration(),)))

    with TestClient(app) as client:
        response = client.get("/api/v1/analysis/templates")

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["template_id"] == "session_metrics"
    assert body["items"][0]["params"][0]["binding"] == ["session_group"]
    assert body["items"][0]["output"]["columns"][0]["name"] == "session_id"


def test_analysis_template_execute(application_facade) -> None:
    result = TemplateResult(
        columns=(TemplateColumn("session_id", "string"),),
        rows=(("a1b2c3",),),
        truncated=False,
    )
    app = create_app(application_facade(analysis_results={"session_metrics": result}))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analysis/templates/session_metrics/execute",
            json={"params": {"session_ids": ["a1b2c3"]}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == [{"name": "session_id", "type": "string"}]
    assert body["rows"] == [["a1b2c3"]]
    assert body["truncated"] is False


def test_analysis_template_execute_unknown_returns_not_found(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analysis/templates/missing/execute",
            json={},
        )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_analysis_template_execute_rejects_invalid_params(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analysis/templates/session_metrics/execute",
            json={"params": {"session_ids": "not-a-list"}},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_failed"
