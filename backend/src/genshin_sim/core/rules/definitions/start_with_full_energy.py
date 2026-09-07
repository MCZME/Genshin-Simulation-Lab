"""开局满元素能量规则。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from genshin_sim.core.rules.errors import RuleValidationError
from genshin_sim.core.rules.models import RuleActivation, RuleResolutionContext
from genshin_sim.core.systems.energy.policies import (
    FullInitialEnergyPolicy,
    InitialEnergyPolicy,
)


class StartWithFullEnergyDefinition:
    """开局把所有角色的标准元素能量设为上限。"""

    rule_key = "start_with_full_energy"
    rule_type: type = InitialEnergyPolicy

    def validate_params(self, params: Mapping[str, Any]) -> None:
        if params:
            raise RuleValidationError("start_with_full_energy 不接受参数")

    def resolve_activation(
        self, activation: RuleActivation, context: RuleResolutionContext
    ) -> InitialEnergyPolicy:
        del activation, context
        return FullInitialEnergyPolicy()
