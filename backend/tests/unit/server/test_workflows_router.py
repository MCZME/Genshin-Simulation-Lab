"""工作流存档 HTTP 路由单元测试。"""

from fastapi.testclient import TestClient

from genshin_sim.application import WorkspaceInfo
from genshin_sim.server import create_app


def test_workflow_crud_round_trip(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/workflows",
            json={"name": "主配队"},
        )
        assert created.status_code == 201
        workflow = created.json()
        assert workflow["name"] == "主配队"
        assert workflow["definition"]["schema_version"] == 1
        assert workflow["definition"]["meta"]["name"] == "主配队"

        listed = client.get("/api/v1/workflows")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [workflow["id"]]

        fetched = client.get(f"/api/v1/workflows/{workflow['id']}")
        assert fetched.status_code == 200
        assert fetched.json() == workflow

        saved = client.put(
            f"/api/v1/workflows/{workflow['id']}",
            json={
                "schema_version": 1,
                "meta": {"name": "新名字"},
                "regions": [],
                "nodes": [],
                "edges": [],
                "layout": {},
            },
        )
        assert saved.status_code == 200
        assert saved.json()["name"] == "新名字"

        deleted = client.delete(f"/api/v1/workflows/{workflow['id']}")
        assert deleted.status_code == 204

        missing = client.get(f"/api/v1/workflows/{workflow['id']}")
        assert missing.status_code == 404
        assert missing.json()["code"] == "not_found"


def test_create_workflow_without_name_uses_default(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        created = client.post("/api/v1/workflows")

    assert created.status_code == 201
    assert created.json()["name"] == "未命名工作流"


def test_workflow_endpoints_require_initialized_workspace(application_facade) -> None:
    app = create_app(
        application_facade(
            workspace=WorkspaceInfo("data", "", False),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/workflows")

    assert response.status_code == 409
    assert response.json()["code"] == "workspace_not_initialized"


def test_workflow_put_rejects_non_object_body(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.put("/api/v1/workflows/wf_1", json=[1, 2, 3])

    assert response.status_code == 400
    assert response.json()["code"] == "validation_failed"
    assert response.json()["details"]
