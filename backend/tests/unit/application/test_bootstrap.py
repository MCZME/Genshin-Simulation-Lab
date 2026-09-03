"""CLI/server application 装配测试。"""

from __future__ import annotations

from genshin_sim.application.facade import DefaultApplicationFacade


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
