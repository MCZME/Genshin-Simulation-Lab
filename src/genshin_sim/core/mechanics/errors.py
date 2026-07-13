from __future__ import annotations


class MechanicSystemError(Exception):
    """机制实例运行时错误基类。"""


class MechanicValidationError(MechanicSystemError, ValueError):
    """机制实例输入或状态不满足契约。"""


class MechanicInstanceNotFoundError(MechanicSystemError, LookupError):
    """请求的机制实例不存在或不处于活动状态。"""


class MechanicAtomicCommitError(MechanicSystemError):
    """机制实例批量提交无法完整应用。"""
