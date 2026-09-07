"""仿真规则系统：装配期规则定义、注册与解析。

规则系统是纯装配期模块：解析激活规则并产出目标系统协议实例，
自身不拥有帧期状态，也不注册为仿真系统。
"""

from genshin_sim.core.rules.definitions import (
    CritModeDefinition,
    StartWithFullEnergyDefinition,
    create_default_rule_registry,
)
from genshin_sim.core.rules.engine import RuleEngine
from genshin_sim.core.rules.errors import (
    DuplicateRuleKeyError,
    DuplicateRuleTypeError,
    RuleSystemError,
    RuleValidationError,
    UnknownRuleKeyError,
)
from genshin_sim.core.rules.models import RuleActivation, RuleResolutionContext
from genshin_sim.core.rules.registry import RuleDefinition, RuleRegistry

__all__ = [
    "CritModeDefinition",
    "DuplicateRuleKeyError",
    "DuplicateRuleTypeError",
    "RuleActivation",
    "RuleDefinition",
    "RuleEngine",
    "RuleRegistry",
    "RuleResolutionContext",
    "RuleSystemError",
    "RuleValidationError",
    "StartWithFullEnergyDefinition",
    "UnknownRuleKeyError",
    "create_default_rule_registry",
]
