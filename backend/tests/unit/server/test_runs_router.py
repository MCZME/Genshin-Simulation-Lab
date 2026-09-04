"""批次运行 HTTP 路由单元测试。"""

from fastapi.testclient import TestClient

from genshin_sim.server import create_app


def _member(item_id: str) -> dict[str, object]:
    return {
        "item_id": item_id,
        "input": {
            "schema_version": 2,
            "kind": "simulation_input",
            "meta": {"name": item_id},
            "team": [],
        },
    }


def test_submit_and_poll_and_cancel_batch(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        submitted = client.post(
            "/api/v1/runs",
            json={
                "name": "扫描",
                "concurrency": 2,
                "members": [_member("e-1"), _member("e-2")],
            },
        )
        assert submitted.status_code == 202
        body = submitted.json()
        assert body["name"] == "扫描"
        assert body["state"] == "completed"
        assert body["concurrency"] == 2
        assert [member["item_id"] for member in body["members"]] == ["e-1", "e-2"]
        assert body["members"][0]["session_id"] == "session-0"

        run_id = body["run_id"]
        polled = client.get(f"/api/v1/runs/{run_id}")
        assert polled.status_code == 200
        assert polled.json()["run_id"] == run_id

        cancelled = client.post(f"/api/v1/runs/{run_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["run_id"] == run_id


def test_submit_run_rejects_invalid_concurrency(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={"concurrency": 0, "members": [_member("e-1")]},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_failed"


def test_submit_run_rejects_duplicate_item_id(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={"members": [_member("e-1"), _member("e-1")]},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "duplicate_item_id"


def test_submit_run_rejects_over_limit_members(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={"members": [_member(f"e-{index}") for index in range(201)]},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "batch_too_large"


def test_get_missing_run_returns_not_found(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_missing")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
