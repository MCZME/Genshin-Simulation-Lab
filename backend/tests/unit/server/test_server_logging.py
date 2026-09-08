"""server 入口日志初始化测试。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from genshin_sim.infrastructure.logging import LoggingSettings, configure_logging
from genshin_sim.server.main import SERVER_LOG_FILE_NAME, _configure_server_logging
from tests.helpers.logging import flush_project_handlers


def _reset_project_logging() -> None:
    configure_logging(LoggingSettings(console_enabled=False))


def test_configure_server_logging_writes_jsonl_to_project_logs(tmp_path: Path):
    try:
        _configure_server_logging(tmp_path)
        logging.getLogger("genshin_sim.server.test").info("server hello")
        flush_project_handlers()
    finally:
        _reset_project_logging()

    log_file = tmp_path / "data" / "logs" / SERVER_LOG_FILE_NAME
    assert log_file.is_file()
    record = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])
    assert record["level"] == "INFO"
    assert record["logger"] == "genshin_sim.server.test"
    assert record["message"] == "server hello"


def test_configure_server_logging_respects_project_config_data_dir(tmp_path: Path):
    (tmp_path / "config.toml").write_text(
        'schema_version = 1\n\n[workspace]\ndata_dir = "custom-data"\n',
        encoding="utf-8",
    )

    try:
        _configure_server_logging(tmp_path)
        logging.getLogger("genshin_sim.server.test").warning("custom data dir")
        flush_project_handlers()
    finally:
        _reset_project_logging()

    log_file = tmp_path / "custom-data" / "logs" / SERVER_LOG_FILE_NAME
    assert log_file.is_file()
    record = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])
    assert record["message"] == "custom data dir"
