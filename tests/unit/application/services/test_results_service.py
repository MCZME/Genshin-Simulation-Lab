from __future__ import annotations

from genshin_sim.application.services import ResultDatabaseService


def test_result_database_service_delegates_initialization(tmp_path):
    calls: list[str] = []

    def init_database(path):
        calls.append(str(path))
        return path

    db_path = tmp_path / "results.db"
    service = ResultDatabaseService(init_database)

    assert service.init_database(db_path) == db_path
    assert calls == [str(db_path)]
