"""批次执行错误。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from genshin_sim.application.errors import ApplicationError


class BatchError(ApplicationError):
    """批次应用能力的基础错误。"""


class BatchValidationError(BatchError, ValueError):
    """批次请求或成员输入校验失败。"""

    def __init__(
        self,
        code: str,
        message: str,
        details: Sequence[Any] = (),
    ) -> None:
        super().__init__(code, message, details)


class BatchRunNotFoundError(BatchError, LookupError):
    """指定批次不存在。"""

    def __init__(self, run_id: str) -> None:
        super().__init__("not_found", f"批次不存在：{run_id}", ({"run_id": run_id},))


BatchNotFoundError = BatchRunNotFoundError


__all__ = [
    "BatchError",
    "BatchNotFoundError",
    "BatchRunNotFoundError",
    "BatchValidationError",
]
