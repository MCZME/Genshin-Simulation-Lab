"""server 启动入口的单元测试。"""

from __future__ import annotations

import pytest

from genshin_sim.server.main import main


def test_server_main_help_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage: genshin-sim-server" in captured.out
