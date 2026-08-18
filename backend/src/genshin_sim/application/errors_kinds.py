"""应用层执行错误的三层分类与稳定错误码。

错误码是批处理调度与结果库之间的稳定契约，不承载 Python 异常类名。
"""

from __future__ import annotations

from enum import StrEnum

from genshin_sim.application.assembly import AssemblyError
from genshin_sim.application.assembly.errors import (
    InvalidRuntimePayloadError,
    MissingRuntimeAssetError,
    MissingRuntimeHandlerError,
)
from genshin_sim.application.errors import ConfigError
from genshin_sim.infrastructure.errors import (
    CancelRaceError,
    ResultWriteError,
    SqliteBusyError,
    WorkerCrashedError,
)


class ExecutionErrorKind(StrEnum):
    """成员执行错误的三层分类。"""

    INPUT = "input"
    EXECUTION = "execution"
    INFRASTRUCTURE = "infrastructure"


INPUT_ERROR_CODES = frozenset(
    {
        "CONFIG_INVALID",
        "ASSET_NOT_FOUND",
        "HANDLER_UNAVAILABLE",
        "VALIDATION_UNAVAILABLE",
    }
)

EXECUTION_ERROR_CODES = frozenset({"SIMULATION_FAILED"})

INFRASTRUCTURE_ERROR_CODES = frozenset(
    {
        "WORKER_CRASHED",
        "RESULT_WRITE_FAILED",
        "SQLITE_BUSY",
        "CANCEL_RACE",
        "SCHEDULING_FAILED",
    }
)


def execution_error_kind(code: str | None) -> ExecutionErrorKind | None:
    """按稳定错误码解析错误类别；未知码返回 None。"""

    if code is None:
        return None
    if code in INPUT_ERROR_CODES:
        return ExecutionErrorKind.INPUT
    if code in EXECUTION_ERROR_CODES:
        return ExecutionErrorKind.EXECUTION
    if code in INFRASTRUCTURE_ERROR_CODES:
        return ExecutionErrorKind.INFRASTRUCTURE
    return None


def is_retryable_error(code: str | None) -> bool:
    """有限重试语义的可重试判定；第一版不自动执行重试。"""

    return code in INFRASTRUCTURE_ERROR_CODES


def execution_error_code(exc: BaseException) -> str:
    """把执行异常翻译为稳定错误码。"""

    if isinstance(exc, MissingRuntimeAssetError):
        return "ASSET_NOT_FOUND"
    if isinstance(exc, MissingRuntimeHandlerError):
        return "HANDLER_UNAVAILABLE"
    if isinstance(exc, ConfigError):
        return "CONFIG_INVALID"
    if isinstance(exc, InvalidRuntimePayloadError):
        return "CONFIG_INVALID"
    if isinstance(exc, AssemblyError):
        return "CONFIG_INVALID"
    if isinstance(exc, SqliteBusyError):
        return "SQLITE_BUSY"
    if isinstance(exc, ResultWriteError):
        return "RESULT_WRITE_FAILED"
    if isinstance(exc, WorkerCrashedError):
        return "WORKER_CRASHED"
    if isinstance(exc, CancelRaceError):
        return "CANCEL_RACE"
    return "SIMULATION_FAILED"


def scheduling_error_code(exc: BaseException) -> str:
    """把批调度层的异常翻译为稳定错误码。"""

    if isinstance(
        exc,
        (
            SqliteBusyError,
            ResultWriteError,
            WorkerCrashedError,
            CancelRaceError,
            AssemblyError,
            ConfigError,
        ),
    ):
        return execution_error_code(exc)
    return "SCHEDULING_FAILED"


__all__ = [
    "EXECUTION_ERROR_CODES",
    "INFRASTRUCTURE_ERROR_CODES",
    "INPUT_ERROR_CODES",
    "ExecutionErrorKind",
    "execution_error_code",
    "execution_error_kind",
    "is_retryable_error",
    "scheduling_error_code",
]
