"""分析查询 HTTP 路由单元测试。"""

from fastapi.testclient import TestClient

from genshin_sim.application import (
    AnalysisColumn,
    AnalysisReadSchema,
    AnalysisSchemaColumn,
    AnalysisSchemaNode,
    AnalysisStageResult,
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
        snapshot_tree=AnalysisSchemaNode(
            key="root",
            label="输入快照",
            kind="object",
            children=(
                AnalysisSchemaNode(
                    key="team",
                    label="队伍",
                    kind="list",
                    children=(
                        AnalysisSchemaNode(
                            key="character",
                            label="角色",
                            kind="object",
                            children=(
                                AnalysisSchemaNode(
                                    key="asset_key",
                                    label="资产",
                                    kind="scalar",
                                    type="string",
                                    default_name_template="char_{0}_key",
                                    value_kind="asset:characters",
                                ),
                            ),
                        ),
                    ),
                ),
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
    assert body["snapshot_tree"]["key"] == "root"
    assert body["snapshot_tree"]["children"][0]["kind"] == "list"
    leaf = body["snapshot_tree"]["children"][0]["children"][0]["children"][0]
    assert leaf["key"] == "asset_key"
    assert leaf["default_name_template"] == "char_{0}_key"
    assert leaf["value_kind"] == "asset:characters"
    assert body["tables"][0]["columns"][0]["value_kind"] == ""


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


def test_analysis_runtime_context_execute_read_close(application_facade) -> None:
    stage_result = AnalysisStageResult(
        stage_id="",
        columns=(AnalysisColumn("session_id", "string"),),
        rows=(("a1b2c3",),),
        truncated=False,
    )
    app = create_app(application_facade(analysis_stage_results={"runs1": stage_result}))

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/analysis/runtime/contexts",
            json={"session_ids": ["a1b2c3"]},
        )
        assert created.status_code == 200
        context_id = created.json()["context_id"]

        executed = client.post(
            f"/api/v1/analysis/runtime/contexts/{context_id}/nodes/execute",
            json={
                "node_id": "runs1",
                "kind": "fetch",
                "params": {"source": "runs"},
                "input_stages": [],
            },
        )
        assert executed.status_code == 200
        body = executed.json()
        assert body["source_node_id"] == "runs1"
        assert body["rows"] == [["a1b2c3"]]

        read = client.get(
            f"/api/v1/analysis/runtime/contexts/{context_id}/stages/{body['stage_id']}"
        )
        assert read.status_code == 200
        assert read.json()["rows"] == [["a1b2c3"]]

        closed = client.delete(f"/api/v1/analysis/runtime/contexts/{context_id}")
        assert closed.status_code == 204

        missing = client.get(
            f"/api/v1/analysis/runtime/contexts/{context_id}/stages/{body['stage_id']}"
        )
        assert missing.status_code == 404


def test_analysis_runtime_select_creates_selection_stage(application_facade) -> None:
    stage_result = AnalysisStageResult(
        stage_id="",
        columns=(AnalysisColumn("session_id", "string"),),
        rows=(("a1b2c3",),),
        truncated=False,
    )
    app = create_app(application_facade(analysis_stage_results={"runs1": stage_result}))

    with TestClient(app) as client:
        context_id = client.post(
            "/api/v1/analysis/runtime/contexts",
            json={"session_ids": ["a1b2c3"]},
        ).json()["context_id"]
        executed = client.post(
            f"/api/v1/analysis/runtime/contexts/{context_id}/nodes/execute",
            json={
                "node_id": "runs1",
                "kind": "fetch",
                "params": {"source": "runs"},
                "input_stages": [],
            },
        ).json()
        selected = client.post(
            (
                f"/api/v1/analysis/runtime/contexts/{context_id}"
                f"/stages/{executed['stage_id']}/select"
            ),
            json={"kind": "row", "row_index": 0},
        )

        assert selected.status_code == 200
        assert selected.json()["rows"] == [["a1b2c3"]]
        assert selected.json()["stage_id"] != executed["stage_id"]


def test_analysis_runtime_merge_concatenates_stages(application_facade) -> None:
    columns = (AnalysisColumn("session_id", "string"),)
    app = create_app(
        application_facade(
            analysis_stage_results={
                "runs1": AnalysisStageResult(
                    stage_id="",
                    columns=columns,
                    rows=(("a",),),
                    truncated=False,
                ),
                "runs2": AnalysisStageResult(
                    stage_id="",
                    columns=columns,
                    rows=(("b",),),
                    truncated=False,
                ),
            }
        )
    )

    with TestClient(app) as client:
        context_id = client.post(
            "/api/v1/analysis/runtime/contexts",
            json={"session_ids": ["a", "b"]},
        ).json()["context_id"]
        left = client.post(
            f"/api/v1/analysis/runtime/contexts/{context_id}/nodes/execute",
            json={
                "node_id": "runs1",
                "kind": "fetch",
                "params": {"source": "runs"},
                "input_stages": [],
            },
        ).json()
        right = client.post(
            f"/api/v1/analysis/runtime/contexts/{context_id}/nodes/execute",
            json={
                "node_id": "runs2",
                "kind": "fetch",
                "params": {"source": "runs"},
                "input_stages": [],
            },
        ).json()
        merged = client.post(
            f"/api/v1/analysis/runtime/contexts/{context_id}/merge",
            json={"stage_ids": [left["stage_id"], right["stage_id"]]},
        )

        assert merged.status_code == 200
        assert sorted(row[0] for row in merged.json()["rows"]) == ["a", "b"]
