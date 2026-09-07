"""内置规则定义与默认注册表。"""

from __future__ import annotations

from genshin_sim.core.rules.definitions.crit_mode import CritModeDefinition
from genshin_sim.core.rules.definitions.start_with_full_energy import (
    StartWithFullEnergyDefinition,
)
from genshin_sim.core.rules.registry import RuleRegistry


def create_default_rule_registry() -> RuleRegistry:
    """创建包含全部内置规则的注册中心。"""

    return RuleRegistry(
        (
            CritModeDefinition(),
            StartWithFullEnergyDefinition(),
        )
    )


__all__ = [
    "CritModeDefinition",
    "StartWithFullEnergyDefinition",
    "create_default_rule_registry",
]
