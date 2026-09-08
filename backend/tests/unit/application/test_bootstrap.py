"""CLI/server application 装配测试。"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from genshin_sim.application.facade import DefaultApplicationFacade
from genshin_sim.infrastructure.jobs import ProcessSimulationJobRunner


def _runner_logs_dir(application: DefaultApplicationFacade) -> Path | None:
    """取装配后进程 runner 的日志目录（infrastructure 接线断言辅助）。"""

    runner = cast(ProcessSimulationJobRunner, application._context.job_runner)
    return runner.logs_dir


def test_server_bootstrap_injects_analysis_stage_executor(tmp_path, monkeypatch) -> None:
    """分析节点运行时依赖必须在真实服务装配中注入，不能依赖可选的 create_application。"""

    from genshin_sim.application.bootstrap import create_server_application

    fake_executor = object()
    monkeypatch.setattr(
        "genshin_sim.application.bootstrap.SQLiteAnalysisStageExecutor",
        lambda result_db: fake_executor,
    )

    application = create_server_application(project_root=tmp_path)

    assert isinstance(application, DefaultApplicationFacade)
    assert application._context.analysis_stage_executor is fake_executor


def test_resolve_logs_dir_uses_project_config(tmp_path: Path) -> None:
    from genshin_sim.application.bootstrap import resolve_logs_dir

    (tmp_path / "config.toml").write_text(
        'schema_version = 1\n\n[workspace]\ndata_dir = "custom-data"\n',
        encoding="utf-8",
    )

    assert resolve_logs_dir(tmp_path) == tmp_path / "custom-data" / "logs"


def test_resolve_logs_dir_falls_back_without_config(tmp_path: Path) -> None:
    from genshin_sim.application.bootstrap import resolve_logs_dir

    assert resolve_logs_dir(tmp_path) == tmp_path / "data" / "logs"


def test_cli_application_enables_worker_logs_only_in_project_mode(tmp_path: Path) -> None:
    from genshin_sim.application.bootstrap import create_cli_application

    without_config = create_cli_application(project_root=tmp_path)
    assert isinstance(without_config, DefaultApplicationFacade)
    assert _runner_logs_dir(without_config) is None

    (tmp_path / "config.toml").write_text(
        'schema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )
    with_config = create_cli_application(project_root=tmp_path)
    assert isinstance(with_config, DefaultApplicationFacade)
    assert _runner_logs_dir(with_config) == tmp_path / "data" / "logs"


def test_server_application_always_enables_worker_logs(tmp_path: Path) -> None:
    from genshin_sim.application.bootstrap import create_server_application

    application = create_server_application(project_root=tmp_path)
    assert isinstance(application, DefaultApplicationFacade)

    assert _runner_logs_dir(application) == tmp_path / "data" / "logs"
