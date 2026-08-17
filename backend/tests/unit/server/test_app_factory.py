"""server app factory 单元测试。"""

from genshin_sim.application import WorkspaceInfo
from genshin_sim.server import create_app


def test_create_app_holds_injected_application(application_facade) -> None:
    application = application_facade(WorkspaceInfo("data", "v1", True))

    app = create_app(application)

    assert app.title == "Genshin Simulation Lab"
    assert app.state.application is application


def test_create_app_returns_independent_instances(application_facade) -> None:
    application = application_facade(WorkspaceInfo("data", "v1", True))

    first = create_app(application)
    second = create_app(application)

    assert first is not second
