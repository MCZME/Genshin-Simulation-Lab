from __future__ import annotations

from dataclasses import dataclass


class ShieldSystemError(Exception):
    """护盾系统错误基类。"""


class ShieldValidationError(ShieldSystemError, ValueError):
    """护盾请求、模型或数值不满足契约。"""


class ShieldAttributeError(ShieldSystemError):
    """护盾公式或动态护盾强效属性解析失败。"""


class ShieldProtectionNotFoundError(ShieldSystemError, LookupError):
    """护盾保护对象在当前运行态中不存在。"""


class ShieldTargetMismatchError(ShieldSystemError):
    """active team 护盾来伤目标不是当前场上角色。"""


class ShieldInstanceNotFoundError(ShieldSystemError, LookupError):
    """护盾实例或组件不存在。"""


class ShieldPolicyError(ShieldSystemError):
    """护盾授予策略与请求状态不匹配。"""


class ShieldCapacityError(ShieldSystemError):
    """护盾容量或有效吸收乘数非法。"""


class ShieldStateConflictError(ShieldSystemError):
    """护盾冲突 key 对应的活动状态不满足策略。"""


class ShieldAtomicCommitError(ShieldSystemError):
    """一次护盾批量提交无法完整应用。"""


@dataclass(frozen=True, slots=True)
class ShieldErrorDetail:
    code: str
    message: str
