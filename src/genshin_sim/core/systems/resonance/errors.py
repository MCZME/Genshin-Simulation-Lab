"""元素共鸣领域的结构化错误。"""

from __future__ import annotations


class ResonanceError(Exception):
    """元素共鸣领域错误基类。"""


class ResonanceValidationError(ResonanceError, ValueError):
    """共鸣模型或请求验证失败。"""


class ResonanceDefinitionNotFoundError(ResonanceError, LookupError):
    """引用不存在的共鸣定义。"""
