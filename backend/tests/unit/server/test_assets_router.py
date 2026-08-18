"""资产查询 HTTP 路由单元测试。"""

from dataclasses import asdict

from fastapi.testclient import TestClient

from genshin_sim.application import AssetListItem, WorkspaceInfo
from genshin_sim.server import create_app

_CHARACTER = AssetListItem(
    asset_key="character:barbara",
    source_id="barbara",
    name="芭芭拉",
    usable=True,
    status=None,
    rarity=4,
    element="Hydro",
    weapon_type="catalyst",
)
_WEAPON = AssetListItem(
    asset_key="weapon:test",
    source_id="test",
    name="测试武器",
    usable=False,
    status="武器实现不可用",
    rarity=5,
    element=None,
    weapon_type="sword",
)
_ARTIFACT_SET = AssetListItem(
    asset_key="artifact_set:test",
    source_id="test",
    name="测试套装",
    usable=True,
    status=None,
    rarity=None,
    element=None,
    weapon_type=None,
)


def test_assets_list_and_detail_do_not_expose_handler_key(application_facade) -> None:
    app = create_app(
        application_facade(
            assets=(_CHARACTER, _WEAPON, _ARTIFACT_SET),
        )
    )

    with TestClient(app) as client:
        listed = client.get(
            "/api/v1/assets/characters",
            params={"q": "芭芭", "limit": 1},
        )
        detail = client.get("/api/v1/assets/characters/barbara")

    assert listed.status_code == 200
    body = listed.json()
    assert body["items"] == [asdict(_CHARACTER)]
    assert "handler_key" not in body["items"][0]

    assert detail.status_code == 200
    assert detail.json() == asdict(_CHARACTER)
    assert "handler_key" not in detail.json()


def test_assets_list_defaults_and_nullable_fields(application_facade) -> None:
    app = create_app(application_facade(assets=(_WEAPON, _ARTIFACT_SET)))

    with TestClient(app) as client:
        weapons = client.get("/api/v1/assets/weapons")
        sets = client.get("/api/v1/assets/artifact-sets")

    assert weapons.json()["items"][0]["element"] is None
    assert sets.json()["items"][0]["rarity"] is None
    assert sets.json()["items"][0]["element"] is None
    assert sets.json()["items"][0]["weapon_type"] is None


def test_assets_unknown_type_returns_not_found(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.get("/api/v1/assets/enemies")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_assets_endpoints_require_initialized_workspace(application_facade) -> None:
    app = create_app(
        application_facade(
            workspace=WorkspaceInfo("data", "", False),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/assets/characters")

    assert response.status_code == 409
    assert response.json()["code"] == "workspace_not_initialized"
