"""分析查询 HTTP 路由单元测试。"""

from fastapi.testclient import TestClient

from genshin_sim.application import (
    AnalysisColumn,
    AnalysisReadSchema,
    AnalysisSchemaColumn,
    AnalysisSnapshotPath,
    AnalysisTableResult,
    AnalysisTableSchema,
)
from genshin_sim.server import create_app


def _schema() -> AnalysisReadSchema:
    return AnalysisReadSchema(
        tables=(
            AnalysisTableSchema(
                name="simulation_runs",
                columns=(AnalysisSchemaColumn("frames_run", "int", "实际运行帧数"),),
            ),
        ),
        event_types=(),
        snapshot_paths=(
            AnalysisSnapshotPath(
                "team.0.character.asset_key",
                "string",
                "char_1_key",
                ("队伍", "槽位 1", "角色", "资产"),
            ),
        ),
    )


def test_analysis_schema_endpoint(application_facade) -> None:
    app = create_app(application_facade(analysis_schema=_schema()))

    with TestClient(app) as client:
        response = client.get("/api/v1/analysis/schema")

    assert response.status_code == 200
    body = response.json()
    assert body["tables"][0]["name"] == "simulation_runs"
    assert body["tables"][0]["columns"][0]["name"] == "frames_run"
    assert body["snapshot_paths"][0]["path"] == "team.0.character.asset_key"
    assert body["snapshot_paths"][0]["default_name"] == "char_1_key"
    assert body["snapshot_paths"][0]["segments"] == ["队伍", "槽位 1", "角色", "资产"]


def test_analysis_query_executes_plan(application_facade) -> None:
    result = AnalysisTableResult(
        columns=(AnalysisColumn("session_id", "string"),),
        rows=(("a1b2c3",),),
        truncated=False,
    )
    app = create_app(application_facade(analysis_plan_results={"c1": result}))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analysis/query",
            json={
                "session_ids": ["a1b2c3"],
                "nodes": [
                    {"id": "runs1", "kind": "fetch", "params": {"source": "runs"}},
                    {
                        "id": "c1",
                        "kind": "limit",
                        "params": {"count": 5},
                        "inputs": ["runs1"],
                    },
                ],
                "outputs": ["c1"],
            },
        )

    assert response.status_code == 200
    body = response.json()
    table = body["tables"]["c1"]
    assert table["columns"] == [{"name": "session_id", "type": "string"}]
    assert table["rows"] == [["a1b2c3"]]
    assert table["truncated"] is False


def test_analysis_query_rejects_unknown_output(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analysis/query",
            json={
                "session_ids": [],
                "nodes": [{"id": "runs1", "kind": "fetch", "params": {"source": "runs"}}],
                "outputs": ["missing"],
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_failed"
