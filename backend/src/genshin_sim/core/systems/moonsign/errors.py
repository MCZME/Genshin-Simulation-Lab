"""月兆领域结构化错误。"""

from __future__ import annotations


class MoonsignError(Exception):
    """月兆领域错误基类。"""


class MoonsignValidationError(MoonsignError, ValueError):
    """月兆模型或请求验证失败。"""


class MoonsignStateConflictError(MoonsignError, RuntimeError):
    """月兆状态写入口冲突。"""
