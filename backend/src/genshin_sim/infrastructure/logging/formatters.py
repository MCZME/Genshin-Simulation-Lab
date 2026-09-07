from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime
from typing import Any

from genshin_sim.infrastructure.logging.context import get_log_context

_RESERVED_RECORD_ATTRIBUTES = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
        "exception",
        "fields",
        "level",
        "logger",
        "message",
        "ts",
    }
)


class JsonFileFormatter(logging.Formatter):
    """把日志记录序列化为单行 JSON（JSON Lines）。"""

    def format(self, record: logging.LogRecord) -> str:
        try:
            return self._format_record(record)
        except Exception as exc:
            fallback = {
                "ts": _format_timestamp(record.created),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "fields": {"format_error": repr(exc)},
                "exception": None,
            }
            return json.dumps(
                fallback,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )

    def _format_record(self, record: logging.LogRecord) -> str:
        fields: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRIBUTES or key.startswith("_"):
                continue
            if value is None or value == "":
                continue
            fields[key] = value
        for key, value in get_log_context().items():
            if value not in ("", None):
                fields[key] = value

        payload: dict[str, Any] = {
            "ts": _format_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "fields": fields,
            "exception": None,
        }
        if record.exc_info is not None and record.exc_info[0] is not None:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info))
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )


def _format_timestamp(created: float) -> str:
    return datetime.fromtimestamp(created).astimezone().isoformat(timespec="milliseconds")
