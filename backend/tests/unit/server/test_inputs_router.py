"""输入校验 HTTP 路由单元测试。"""

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


def test_validate_inputs_returns_member_report(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/inputs/validate",
            json={"members": [_member("e-1"), _member("e-2")]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert [member["item_id"] for member in body["members"]] == ["e-1", "e-2"]
    assert all(member["ok"] is True for member in body["members"])


def test_validate_inputs_rejects_duplicate_item_id(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/inputs/validate",
            json={"members": [_member("e-1"), _member("e-1")]},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "duplicate_item_id"


def test_validate_inputs_rejects_over_limit_members(application_facade) -> None:
    app = create_app(application_facade())
    members = [_member(f"e-{index}") for index in range(201)]

    with TestClient(app) as client:
        response = client.post("/api/v1/inputs/validate", json={"members": members})

    assert response.status_code == 400
    assert response.json()["code"] == "batch_too_large"


def test_validate_inputs_rejects_empty_members(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.post("/api/v1/inputs/validate", json={"members": []})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_failed"
