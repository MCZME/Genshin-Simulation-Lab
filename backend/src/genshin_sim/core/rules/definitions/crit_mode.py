"""暴击模式规则。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from genshin_sim.core.rules.errors import RuleValidationError
from genshin_sim.core.rules.models import RuleActivation, RuleResolutionContext
from genshin_sim.core.systems.damage.enums import CritOutcome
from genshin_sim.core.systems.damage.policies import (
    CriticalDecisionProvider,
    FixedCriticalDecisionProvider,
    SeededRandomCriticalDecisionProvider,
)

CRIT_MODE_OFF = "off"
CRIT_MODE_RANDOM = "random"
SUPPORTED_CRIT_MODES = (CRIT_MODE_OFF, CRIT_MODE_RANDOM)


class CritModeDefinition:
    """选择暴击判定模式。

    ``off`` 固定不暴击（与默认行为一致），``random`` 按运行选项种子确定性随机判定。
    """

    rule_key = "crit_mode"
    rule_type: type = CriticalDecisionProvider

    def validate_params(self, params: Mapping[str, Any]) -> None:
        unknown = set(params) - {"mode"}
        if unknown:
            raise RuleValidationError(f"crit_mode 包含未知参数：{', '.join(sorted(unknown))}")
        mode = params.get("mode", CRIT_MODE_OFF)
        if mode not in SUPPORTED_CRIT_MODES:
            raise RuleValidationError(
                f"crit_mode.mode 必须是 {' 或 '.join(SUPPORTED_CRIT_MODES)}：{mode}"
            )

    def resolve_activation(
        self, activation: RuleActivation, context: RuleResolutionContext
    ) -> CriticalDecisionProvider:
        mode = activation.params.get("mode", CRIT_MODE_OFF)
        if mode == CRIT_MODE_RANDOM:
            return SeededRandomCriticalDecisionProvider(context.seed)
        return FixedCriticalDecisionProvider(CritOutcome.NON_CRITICAL)
