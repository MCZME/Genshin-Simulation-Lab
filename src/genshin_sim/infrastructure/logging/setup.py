from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from genshin_sim.infrastructure.logging.context import LogContextFilter
from genshin_sim.infrastructure.logging.formatters import JsonFileFormatter
from genshin_sim.infrastructure.logging.settings import LoggingSettings, coerce_log_level

_MANAGED_HANDLER_ATTR = "_genshin_sim_managed_handler"
_LOG_FILE_PREFIX = "genshin-sim"
_LOG_FILE_SUFFIX = ".jsonl"


def configure_logging(settings: LoggingSettings | None = None) -> logging.Logger:
    """配置项目包日志器并返回配置后的日志器。"""

    resolved = settings or LoggingSettings()
    logger = logging.getLogger(resolved.package_logger_name)
    logger.setLevel(coerce_log_level(resolved.level))
    logger.propagate = resolved.propagate

    _remove_managed_handlers(logger)

    text_formatter = logging.Formatter(
        fmt=resolved.message_format,
        datefmt=resolved.date_format,
    )
    json_formatter = JsonFileFormatter()

    if resolved.console_enabled:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(coerce_log_level(resolved.console_level))
        _prepare_handler(console_handler, text_formatter)
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
        _prepare_handler(file_handler, json_formatter)
        logger.addHandler(file_handler)

    if resolved.file_dir is not None:
        log_dir = resolved.file_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        file_path = _new_log_file_path(log_dir)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(coerce_log_level(resolved.file_level))
        _cleanup_log_files(
            log_dir,
            max_age_days=resolved.max_log_age_days,
            max_file_count=resolved.max_log_file_count,
            logger=logger,
        )
        _prepare_handler(file_handler, json_formatter)
        logger.addHandler(file_handler)

    return logger


def _cleanup_log_files(
    log_dir: Path,
    *,
    max_age_days: int,
    max_file_count: int,
    logger: logging.Logger,
) -> None:
    """删除过期和超量的日志文件；只作用于 logs 目录自身，失败只记警告。"""

    try:
        cutoff = datetime.now().astimezone() - timedelta(days=max_age_days)
        files = sorted(
            (
                path
                for path in log_dir.glob(f"{_LOG_FILE_PREFIX}-*{_LOG_FILE_SUFFIX}")
                if path.is_file()
            ),
            key=lambda path: path.stat().st_mtime,
        )
        for path in files:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
            if modified_at < cutoff:
                path.unlink()
        remaining = [path for path in files if path.exists()]
        for path in remaining[: max(0, len(remaining) - max_file_count)]:
            path.unlink()
    except OSError as exc:
        logger.warning("日志清理失败", extra={"log_dir": str(log_dir), "error": str(exc)})


def _new_log_file_path(log_dir: Path) -> Path:
    now = datetime.now().astimezone()
    stamp = f"{now:%Y-%m-%dT%H-%M-%S}.{now.microsecond // 1000:03d}"
    path = log_dir / f"{_LOG_FILE_PREFIX}-{stamp}-{os.getpid()}{_LOG_FILE_SUFFIX}"
    if path.exists():
        path = (
            log_dir
            / f"{_LOG_FILE_PREFIX}-{stamp}-{os.getpid()}-{uuid.uuid4().hex[:8]}{_LOG_FILE_SUFFIX}"
        )
    return path


def _prepare_handler(handler: logging.Handler, formatter: logging.Formatter) -> None:
    handler.setFormatter(formatter)
    handler.addFilter(LogContextFilter())
    setattr(handler, _MANAGED_HANDLER_ATTR, True)


def _remove_managed_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, _MANAGED_HANDLER_ATTR, False):
            logger.removeHandler(handler)
            handler.close()
