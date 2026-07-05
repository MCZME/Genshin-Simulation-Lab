from __future__ import annotations

import logging

import pytest

from genshin_sim.infrastructure.logging import (
    LoggingSettings,
    coerce_log_level,
    configure_logging,
    logging_context,
)


@pytest.fixture(autouse=True)
def reset_project_logging():
    configure_logging(LoggingSettings(console_enabled=False))
    yield
    configure_logging(LoggingSettings(console_enabled=False))


def test_configure_logging_writes_context_to_file(tmp_path):
    log_path = tmp_path / "app.log"
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
        logger.info("hello log")

    _flush_project_handlers()

    text = log_path.read_text(encoding="utf-8")
    assert "INFO genshin_sim.test" in text
    assert "command=config.validate" in text
    assert "operation_id=op-1" in text
    assert "session_id=sess-1" in text
    assert "hello log" in text


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


def _flush_project_handlers() -> None:
    for handler in logging.getLogger("genshin_sim").handlers:
        handler.flush()
