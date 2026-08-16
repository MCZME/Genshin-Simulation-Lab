from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import pytest

from genshin_sim.infrastructure.logging import (
    LoggingSettings,
    coerce_log_level,
    configure_logging,
    logging_context,
)
from tests.helpers.logging import flush_project_handlers


@pytest.fixture(autouse=True)
def reset_project_logging():
    configure_logging(LoggingSettings(console_enabled=False))
    yield
    configure_logging(LoggingSettings(console_enabled=False))


def test_configure_logging_writes_jsonl_to_file(tmp_path):
    log_path = tmp_path / "app.jsonl"
    configure_logging(
        LoggingSettings(
            level="DEBUG",
            console_enabled=False,
            file_path=log_path,
            file_level="DEBUG",
        )
    )

    logger = logging.getLogger("genshin_sim.test")
    with logging_context(command="config.validate", operation_id="op-1", session_id="sess-1"):
        logger.info("hello log", extra={"config_name": "demo"})

    flush_project_handlers()

    text = log_path.read_text(encoding="utf-8")
    record = json.loads(text.splitlines()[0])
    assert record["level"] == "INFO"
    assert record["logger"] == "genshin_sim.test"
    assert record["message"] == "hello log"
    assert record["fields"]["command"] == "config.validate"
    assert record["fields"]["operation_id"] == "op-1"
    assert record["fields"]["session_id"] == "sess-1"
    assert record["fields"]["config_name"] == "demo"
    assert record["exception"] is None


def test_file_dir_creates_per_invocation_jsonl_file(tmp_path):
    log_dir = tmp_path / "logs"
    configure_logging(
        LoggingSettings(
            console_enabled=False,
            file_dir=log_dir,
            file_level="DEBUG",
        )
    )

    logger = logging.getLogger("genshin_sim.test")
    logger.info("per invocation")

    flush_project_handlers()

    files = list(log_dir.glob("genshin-sim-*.jsonl"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert record["message"] == "per invocation"


def test_file_dir_cleanup_removes_old_and_excess_files(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    old = log_dir / "genshin-sim-2020-01-01T00-00-00.000-1.jsonl"
    old.write_text("old\n", encoding="utf-8")
    old_timestamp = datetime(2020, 1, 1).timestamp()
    os.utime(old, (old_timestamp, old_timestamp))
    for index in range(3):
        path = log_dir / f"genshin-sim-2026-08-11T10-00-0{index}.000-{index}.jsonl"
        path.write_text("recent\n", encoding="utf-8")

    configure_logging(
        LoggingSettings(
            console_enabled=False,
            file_dir=log_dir,
            max_log_age_days=30,
            max_log_file_count=2,
        )
    )

    remaining = list(log_dir.glob("genshin-sim-*.jsonl"))
    assert len(remaining) == 2
    assert not any(path.name.startswith("genshin-sim-2020-") for path in remaining)


def test_json_formatter_handles_exception_and_non_serializable(tmp_path):
    log_path = tmp_path / "app.jsonl"
    configure_logging(
        LoggingSettings(
            console_enabled=False,
            file_path=log_path,
            file_level="ERROR",
        )
    )

    logger = logging.getLogger("genshin_sim.test")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logger.error("失败", exc_info=True, extra={"db_path": Path("/tmp/x.db")})

    flush_project_handlers()

    record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(record["fields"]["db_path"], str)
    assert record["fields"]["db_path"].endswith("x.db")
    assert "Traceback" in record["exception"]
    assert "RuntimeError: boom" in record["exception"]


def test_configure_logging_replaces_managed_handlers():
    project_logger = configure_logging(
        LoggingSettings(level="DEBUG", console_enabled=True, console_level="DEBUG")
    )
    first_handlers = _managed_handlers(project_logger)

    configure_logging(LoggingSettings(level="INFO", console_enabled=True, console_level="INFO"))
    second_handlers = _managed_handlers(project_logger)

    assert len(first_handlers) == 1
    assert len(second_handlers) == 1
    assert second_handlers[0] is not first_handlers[0]


def test_coerce_log_level_rejects_unknown_level():
    with pytest.raises(ValueError, match="不支持的日志级别"):
        coerce_log_level("verbose")


def _managed_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [
        handler
        for handler in logger.handlers
        if getattr(handler, "_genshin_sim_managed_handler", False)
    ]
