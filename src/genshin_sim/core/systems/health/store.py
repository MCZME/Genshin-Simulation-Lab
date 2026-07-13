from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.attributes import AttributeSubjectKind, AttributeSubjectRef
from genshin_sim.core.entity_states import HealthState
from genshin_sim.core.systems.health.errors import (
    CharacterHealthNotFoundError,
    HealthValidationError,
    UnsupportedHealthSubjectError,
)


class CharacterHealthStore:
    """按角色属性主体引用索引角色生命状态。"""

    __slots__ = ("_health_by_ref",)

    def __init__(
        self,
        entries: Iterable[tuple[AttributeSubjectRef, HealthState]] = (),
    ) -> None:
        health_by_ref: dict[AttributeSubjectRef, HealthState] = {}
        for character_ref, health in entries:
            _validate_character_ref(character_ref)
            if not isinstance(health, HealthState):
                raise HealthValidationError("角色生命索引值必须是 HealthState")
            if character_ref in health_by_ref:
                raise HealthValidationError(f"角色生命主体重复：{character_ref.entity_id}")
            health_by_ref[character_ref] = health
        self._health_by_ref = health_by_ref

    def get(self, character_ref: AttributeSubjectRef) -> HealthState | None:
        _validate_character_ref(character_ref)
        return self._health_by_ref.get(character_ref)

    def require(self, character_ref: AttributeSubjectRef) -> HealthState:
        health = self.get(character_ref)
        if health is None:
            raise CharacterHealthNotFoundError(f"角色生命状态不存在：{character_ref.entity_id}")
        return health

    def contains(self, character_ref: AttributeSubjectRef) -> bool:
        _validate_character_ref(character_ref)
        return character_ref in self._health_by_ref


def _validate_character_ref(character_ref: AttributeSubjectRef) -> None:
    if not isinstance(character_ref, AttributeSubjectRef):
        raise HealthValidationError("生命主体引用必须是 AttributeSubjectRef")
    if character_ref.kind is not AttributeSubjectKind.CHARACTER:
        raise UnsupportedHealthSubjectError("生命系统只支持角色主体")
