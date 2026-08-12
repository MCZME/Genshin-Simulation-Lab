"""Flet 用户界面入口和视图层。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import flet as ft

from genshin_sim.application.services import (
    InputValidationService,
    ResultsService,
    SimulationInputValidator,
    SimulationTaskService,
)


class PageLike(Protocol):
    """The small Flet page surface used by the MVP shell."""

    title: str

    def add(self, *controls: object) -> None: ...


@dataclass(frozen=True, slots=True)
class UIServices:
    """Application services injected into the UI layer."""

    config_validator: SimulationInputValidator
    results: ResultsService | None = None
    simulation_tasks: SimulationTaskService | None = None


def create_default_ui_services() -> UIServices:
    """Create only services that do not require infrastructure adapters."""

    return UIServices(config_validator=InputValidationService())


def build_shell(page: PageLike, services: UIServices) -> None:
    """Build the temporary Flet shell without touching SQLite or core objects."""

    del services
    page.title = "Genshin Simulation Lab"
    page.add(ft.Text("Genshin Simulation Lab"))


def main(services: UIServices | None = None) -> None:
    """Run the Flet shell."""

    resolved_services = services or create_default_ui_services()
    ft.app(target=lambda page: build_shell(page, resolved_services))


__all__ = [
    "UIServices",
    "build_shell",
    "create_default_ui_services",
    "main",
]
