"""治疗系统的结构化错误。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HealingErrorDetail:
    """向上层暴露的结构化治疗错误摘要。"""

    code: str
    message: str


class HealingSystemError(Exception):
    """治疗系统错误基类，统一提供稳定错误码。"""

    code = "healing_error"

    @property
    def detail(self) -> HealingErrorDetail:
        """返回适合应用层或测试断言使用的错误详情。"""

        return HealingErrorDetail(self.code, str(self))


class HealingValidationError(HealingSystemError, ValueError):
    """治疗请求、公式输入或结果模型字段不合法。"""

    code = "healing_validation_error"


class UnsupportedHealingSubjectError(HealingValidationError):
    """治疗来源或目标不是第一版支持的角色主体。"""

    code = "unsupported_healing_subject"


class InvalidHealingAttributeError(HealingValidationError):
    """治疗公式无法合法解析所需属性。"""

    code = "invalid_healing_attribute"


class InvalidHealingResultError(HealingValidationError):
    """治疗公式产生了非法结果。"""

    code = "invalid_healing_result"
