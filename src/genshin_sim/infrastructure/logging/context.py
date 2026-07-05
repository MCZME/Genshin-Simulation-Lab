from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

DEFAULT_LOG_CONTEXT = {
    "command": "",
    "operation_id": "",
    "session_id": "",
    "config_name": "",
    "asset_db": "",
    "result_db": "",
}

_log_context: ContextVar[dict[str, str] | None] = ContextVar(
    "genshin_sim_log_context",
    default=None,
)


def get_log_context() -> dict[str, str]:
    """返回当前日志上下文，并补齐默认字段。"""

    return {**DEFAULT_LOG_CONTEXT, **(_log_context.get() or {})}


@contextmanager
def logging_context(**fields: Any) -> Iterator[None]:
    """临时给日志记录附加诊断字段。"""

    current = _log_context.get() or {}
    merged = {
        **current,
        **{key: str(value) for key, value in fields.items() if value is not None},
    }
    token = _log_context.set(merged)
    try:
        yield
    finally:
        _log_context.reset(token)


class LogContextFilter(logging.Filter):
    """为每条日志记录补齐项目约定的上下文字段。"""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_log_context().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True
