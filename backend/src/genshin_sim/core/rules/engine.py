"""规则引擎：把激活列表解析为按规则类型索引的产物束。"""

from __future__ import annotations

from typing import Any

from genshin_sim.core.rules.errors import (
    DuplicateRuleTypeError,
    RuleValidationError,
)
from genshin_sim.core.rules.models import RuleActivation, RuleResolutionContext
from genshin_sim.core.rules.registry import RuleRegistry


class RuleEngine:
    """解析激活规则并产出规则类型束。"""

    def __init__(self, registry: RuleRegistry) -> None:
        self.registry = registry

    def resolve(
        self,
        activations: tuple[RuleActivation, ...],
        context: RuleResolutionContext,
    ) -> dict[type, Any]:
        """解析全部激活规则，返回以规则类型为键的产物束。"""

        bundle: dict[type, Any] = {}
        producers: dict[type, str] = {}
        activated_keys: set[str] = set()
        for activation in activations:
            if activation.rule_key in activated_keys:
                raise RuleValidationError(f"规则重复激活：{activation.rule_key}")
            activated_keys.add(activation.rule_key)
            definition = self.registry.require(activation.rule_key)
            definition.validate_params(activation.params)
            product = definition.resolve_activation(activation, context)
            rule_type = definition.rule_type
            if not isinstance(product, rule_type):
                raise RuleValidationError(
                    f"规则 {activation.rule_key} 的产物不符合声明的规则类型：{rule_type.__name__}"
                )
            existing_producer = producers.get(rule_type)
            if existing_producer is not None:
                raise DuplicateRuleTypeError(
                    f"规则类型 {rule_type.__name__} 已由规则 {existing_producer} 产出，"
                    f"规则 {activation.rule_key} 不能再次产出"
                )
            producers[rule_type] = activation.rule_key
            bundle[rule_type] = product
        return bundle
