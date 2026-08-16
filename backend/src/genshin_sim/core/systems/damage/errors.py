"""伤害系统的结构化错误。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DamageErrorDetail:
    """向上层暴露的结构化伤害错误摘要。"""

    code: str
    message: str


class DamageSystemError(Exception):
    """伤害系统错误基类，统一提供稳定错误码。"""

    code = "damage_system_error"

    @property
    def detail(self) -> DamageErrorDetail:
        """返回适合应用层或测试断言使用的错误详情。"""

        return DamageErrorDetail(self.code, str(self))


class DamageValidationError(DamageSystemError, ValueError):
    """伤害请求、修饰项或结果模型字段不合法。"""

    code = "damage_validation_error"


class UnsupportedDamageElementError(DamageValidationError):
    """伤害元素缺失或不属于第一版支持范围。"""

    code = "unsupported_damage_element"


class DuplicateDamageFormulaError(DamageSystemError):
    """同一种伤害类型被重复注册了完整公式。"""

    code = "duplicate_damage_formula"


class UnsupportedDamageTypeError(DamageValidationError):
    """请求的伤害类型尚未注册可用公式。"""

    code = "unsupported_damage_type"


class DamageFormulaInputError(DamageValidationError):
    """伤害请求不满足当前公式的输入契约。"""

    code = "damage_formula_input_error"


class DamageSourceNotFoundError(DamageSystemError, LookupError):
    """运行时无法解析伤害来源。"""

    code = "damage_source_not_found"


class DamageTargetNotFoundError(DamageSystemError, LookupError):
    """运行时无法解析伤害目标。"""

    code = "damage_target_not_found"


class InvalidDamageScalingError(DamageValidationError):
    """基础伤害倍率契约不合法。"""

    code = "invalid_damage_scaling"


class DamageProviderViolationError(DamageSystemError):
    """伤害修饰 provider 越权读取或返回非法 term。"""

    code = "damage_provider_violation"


class ConflictingDamageModifierError(DamageSystemError):
    """伤害修饰项之间存在无法自动处理的叠加冲突。"""

    code = "conflicting_damage_modifier"


class CriticalDecisionError(DamageSystemError):
    """暴击决策 provider 返回了与请求不兼容的结果。"""

    code = "critical_decision_error"


class DamageResolutionError(DamageSystemError):
    """伤害结算过程中出现无法生成有效数值的错误。"""

    code = "damage_resolution_error"
