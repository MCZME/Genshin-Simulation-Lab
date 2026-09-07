from __future__ import annotations

from genshin_sim.application.services import ProjectService
from tests.helpers.project import FakeProjectConfigStore


def test_project_service_load_project(tmp_path):
    service = ProjectService(FakeProjectConfigStore(data_dir="lab"))

    config = service.load_project(tmp_path)

    assert config.workspace.data_dir == "lab"


def test_project_service_workspace_paths(tmp_path):
    service = ProjectService(FakeProjectConfigStore(data_dir="lab"))

    paths = service.workspace_paths(tmp_path)

    assert paths["inputs"] == tmp_path / "lab" / "inputs"
    assert paths["results_db"] == tmp_path / "lab" / "results" / "results.db"
    assert paths["logs"] == tmp_path / "lab" / "logs"
