from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

LogLevel = int | str

DEFAULT_LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "command=%(command)s operation_id=%(operation_id)s session_id=%(session_id)s "
    "config_name=%(config_name)s asset_db=%(asset_db)s result_db=%(result_db)s "
    "%(message)s"
)
DEFAULT_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    """项目包日志器的配置。"""

    package_logger_name: str = "genshin_sim"
    level: LogLevel = logging.INFO
    console_enabled: bool = True
    console_level: LogLevel = logging.WARNING
    file_path: Path | None = None
    file_level: LogLevel = logging.INFO
    max_bytes: int = 5 * 1024 * 1024
    backup_count: int = 5
    message_format: str = DEFAULT_LOG_FORMAT
    date_format: str = DEFAULT_DATE_FORMAT
    propagate: bool = False


def coerce_log_level(level: LogLevel) -> int:
    """把日志级别名称或数值归一化为标准数值。"""

    if isinstance(level, int):
        return level

    value = logging.getLevelNamesMapping().get(level.upper())
    if isinstance(value, int):
        return value
    raise ValueError(f"不支持的日志级别：{level}")
