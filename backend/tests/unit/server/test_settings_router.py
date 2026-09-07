"""界面偏好与开发者设置 HTTP 路由单元测试。"""

from fastapi.testclient import TestClient

from genshin_sim.application.config import DeveloperConfig
from genshin_sim.server import create_app


def test_get_settings_returns_defaults(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.get("/api/v1/settings")

    assert response.status_code == 200
    assert response.json() == {
        "run_animation": True,
        "developer": {"enabled": False},
        "workspace": {"data_dir": "data"},
    }


def test_put_settings_saves_and_returns_new_value(application_facade) -> None:
    facade = application_facade()
    app = create_app(facade)

    with TestClient(app) as client:
        updated = client.put(
            "/api/v1/settings",
            json={"run_animation": False, "developer_enabled": True},
        )
        fetched = client.get("/api/v1/settings")

    assert updated.status_code == 200
    assert updated.json() == {
        "run_animation": False,
        "developer": {"enabled": True},
        "workspace": {"data_dir": "data"},
    }
    # GET 在 PUT 之后返回新值，证明 save 已生效
    assert fetched.json() == {
        "run_animation": False,
        "developer": {"enabled": True},
        "workspace": {"data_dir": "data"},
    }


def test_put_settings_persists_developer_flag_to_config(application_facade) -> None:
    facade = application_facade()
    app = create_app(facade)

    with TestClient(app) as client:
        client.put(
            "/api/v1/settings",
            json={"run_animation": True, "developer_enabled": True},
        )

    reloaded = facade.get_developer_settings()
    assert reloaded.enabled is True


def test_put_settings_without_developer_field_keeps_current_flag(application_facade) -> None:
    """兼容既有前端：只发送 run_animation 时开发者模式保持不变。"""

    facade = application_facade(developer_settings=DeveloperConfig(enabled=True))
    app = create_app(facade)

    with TestClient(app) as client:
        client.put("/api/v1/settings", json={"run_animation": False})

    assert facade.saved_developer_settings == []
    assert facade.get_developer_settings().enabled is True
