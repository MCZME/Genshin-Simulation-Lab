"""元素共鸣定义注册表。"""

from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.systems.resonance.errors import (
    ResonanceDefinitionNotFoundError,
    ResonanceValidationError,
)
from genshin_sim.core.systems.resonance.models import ResonanceDefinition


class ResonanceDefinitionRegistry:
    """组装期只读的共鸣定义注册表。"""

    def __init__(self, definitions: Iterable[ResonanceDefinition] = ()) -> None:
        self._definitions: dict[str, ResonanceDefinition] = {}
        for definition in definitions:
            self.register(definition)

    @property
    def definitions(self) -> tuple[ResonanceDefinition, ...]:
        return tuple(self._definitions.values())

    def register(self, definition: ResonanceDefinition) -> ResonanceDefinition:
        if not isinstance(definition, ResonanceDefinition):
            raise ResonanceValidationError("共鸣定义必须是 ResonanceDefinition")
        if definition.key in self._definitions:
            raise ResonanceValidationError(f"重复共鸣定义：{definition.key}")
        self._definitions[definition.key] = definition
        return definition

    def get(self, key: str) -> ResonanceDefinition:
        try:
            return self._definitions[key]
        except KeyError as exc:
            raise ResonanceDefinitionNotFoundError(f"未知共鸣定义：{key}") from exc

    def contains(self, key: str) -> bool:
        return key in self._definitions
