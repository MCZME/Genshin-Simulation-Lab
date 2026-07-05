from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from genshin_sim.infrastructure.logging.context import LogContextFilter
from genshin_sim.infrastructure.logging.settings import LoggingSettings, coerce_log_level

_MANAGED_HANDLER_ATTR = "_genshin_sim_managed_handler"


def configure_logging(settings: LoggingSettings | None = None) -> logging.Logger:
    """配置项目包日志器并返回配置后的日志器。"""

    resolved = settings or LoggingSettings()
    logger = logging.getLogger(resolved.package_logger_name)
    logger.setLevel(coerce_log_level(resolved.level))
    logger.propagate = resolved.propagate

    _remove_managed_handlers(logger)

    formatter = logging.Formatter(
        fmt=resolved.message_format,
        datefmt=resolved.date_format,
    )

    if resolved.console_enabled:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(coerce_log_level(resolved.console_level))
        _prepare_handler(console_handler, formatter)
        logger.addHandler(console_handler)

    if resolved.file_path is not None:
        resolved.file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            resolved.file_path,
            maxBytes=resolved.max_bytes,
            backupCount=resolved.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(coerce_log_level(resolved.file_level))
        _prepare_handler(file_handler, formatter)
        logger.addHandler(file_handler)

    return logger


def _prepare_handler(handler: logging.Handler, formatter: logging.Formatter) -> None:
    handler.setFormatter(formatter)
    handler.addFilter(LogContextFilter())
    setattr(handler, _MANAGED_HANDLER_ATTR, True)


def _remove_managed_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, _MANAGED_HANDLER_ATTR, False):
            logger.removeHandler(handler)
            handler.close()
