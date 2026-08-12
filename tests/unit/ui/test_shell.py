from __future__ import annotations

from pathlib import Path

import flet as ft

from genshin_sim.application.services import InputValidationService
from genshin_sim.ui import UIServices, build_shell, create_default_ui_services


class FakePage:
    def __init__(self) -> None:
        self.title = ""
        self.controls: list[object] = []

    def add(self, *controls: object) -> None:
        self.controls.extend(controls)


def test_create_default_ui_services_only_builds_application_service_shell():
    services = create_default_ui_services()

    assert isinstance(services.config_validator, InputValidationService)
    assert services.results is None
    assert services.simulation_tasks is None


def test_build_shell_renders_minimal_flet_surface():
    page = FakePage()

    build_shell(
        page,
        UIServices(config_validator=InputValidationService()),
    )

    assert page.title == "Genshin Simulation Lab"
    assert len(page.controls) == 1
    assert isinstance(page.controls[0], ft.Text)


def test_ui_shell_does_not_import_infrastructure_or_core_runtime():
    source = Path("src/genshin_sim/ui/__init__.py").read_text(encoding="utf-8")

    assert "genshin_sim.infrastructure" not in source
    assert "sqlite3" not in source
    assert "genshin_sim.core" not in source
