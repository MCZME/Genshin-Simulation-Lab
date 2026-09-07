"""基础设施层的稳定执行错误。

这些错误用于把 SQLite、进程等外部故障翻译为批处理与结果库使用的
稳定错误码，避免把 Python 异常类名或本地路径当作对外契约。
"""

from __future__ import annotations


class InfrastructureExecutionError(Exception):
    """可归入稳定错误码的基础设施执行故障。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ResultWriteError(InfrastructureExecutionError):
    """结果写入失败或超时。"""

    def __init__(self, message: str, *, code: str = "RESULT_WRITE_FAILED") -> None:
        super().__init__(code, message)


class SqliteBusyError(InfrastructureExecutionError):
    """SQLite 写锁竞争在重试窗口内未缓解。"""

    def __init__(self, message: str = "结果库写入繁忙") -> None:
        super().__init__("SQLITE_BUSY", message)


class WorkerCrashedError(InfrastructureExecutionError):
    """执行 worker 异常退出。"""

    def __init__(self, message: str = "仿真执行 worker 崩溃") -> None:
        super().__init__("WORKER_CRASHED", message)


class CancelRaceError(InfrastructureExecutionError):
    """取消与执行状态竞争的调度故障。"""

    def __init__(self, message: str = "取消请求与执行状态冲突") -> None:
        super().__init__("CANCEL_RACE", message)


__all__ = [
    "CancelRaceError",
    "InfrastructureExecutionError",
    "ResultWriteError",
    "SqliteBusyError",
    "WorkerCrashedError",
]
