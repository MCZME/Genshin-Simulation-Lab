"""规则定义注册中心。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from genshin_sim.core.rules.errors import DuplicateRuleKeyError, UnknownRuleKeyError
from genshin_sim.core.rules.models import RuleActivation, RuleResolutionContext


class RuleDefinition(Protocol):
    """一条规则的定义契约。

    ``rule_key`` 是规则稳定标识；``rule_type`` 是该规则产物的规则类型，
    引擎按 ``rule_type`` 把产物路由到目标系统，产物必须是 ``rule_type`` 的实例。
    """

    rule_key: str
    rule_type: type

    def validate_params(self, params: Mapping[str, Any]) -> None:
        """校验激活参数；非法时抛出 RuleValidationError。"""
        ...

    def resolve_activation(self, activation: RuleActivation, context: RuleResolutionContext) -> Any:
        """产出目标系统协议实例。"""
        ...


class RuleRegistry:
    """规则定义的唯一注册中心。"""

    def __init__(self, definitions: Iterable[RuleDefinition] = ()) -> None:
        self._definitions: dict[str, RuleDefinition] = {}
        for definition in definitions:
            self.register(definition)

    @property
    def definitions(self) -> tuple[RuleDefinition, ...]:
        return tuple(self._definitions.values())

    @property
    def rule_keys(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def register(self, definition: RuleDefinition) -> None:
        rule_key = definition.rule_key
        if rule_key in self._definitions:
            raise DuplicateRuleKeyError(f"规则 key 已注册：{rule_key}")
        self._definitions[rule_key] = definition

    def require(self, rule_key: str) -> RuleDefinition:
        definition = self._definitions.get(rule_key)
        if definition is None:
            raise UnknownRuleKeyError(f"未注册的规则：{rule_key}")
        return definition
