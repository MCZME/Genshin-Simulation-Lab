from __future__ import annotations

from collections.abc import Iterable, Mapping

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.entity_states.energy import EnergyState
from genshin_sim.core.systems.energy.errors import (
    CharacterEnergyNotFoundError,
    DuplicateEnergyRequestError,
    EnergyPlanConflictError,
    EnergyValidationError,
)
from genshin_sim.core.systems.energy.models import CharacterEnergyProfile, validate_character_ref


class CharacterEnergyStore:
    """角色元素能量档案和可变状态的唯一索引。"""

    __slots__ = ("_committed_operation_ids", "_entries", "_version")

    def __init__(
        self,
        entries: Iterable[tuple[CharacterEnergyProfile, EnergyState]],
    ) -> None:
        result: dict[AttributeSubjectRef, tuple[CharacterEnergyProfile, EnergyState]] = {}
        for profile, state in entries:
            if not isinstance(profile, CharacterEnergyProfile):
                raise EnergyValidationError("角色能量档案必须是 CharacterEnergyProfile")
            if not isinstance(state, EnergyState):
                raise EnergyValidationError("角色能量状态必须是 EnergyState")
            if profile.character_ref in result:
                raise EnergyValidationError(f"角色能量主体重复：{profile.character_ref.entity_id}")
            if state.current_energy > profile.capacity:
                raise EnergyValidationError("当前元素能量不能超过 capacity")
            if profile.capacity == 0.0 and state.current_energy != 0.0:
                raise EnergyValidationError("capacity 为 0 的角色当前元素能量必须为 0")
            result[profile.character_ref] = (profile, state)
        self._entries = result
        self._version = 0
        self._committed_operation_ids: set[str] = set()

    @property
    def version(self) -> int:
        return self._version

    @property
    def refs(self) -> tuple[AttributeSubjectRef, ...]:
        return tuple(self._entries)

    def contains(self, character_ref: AttributeSubjectRef) -> bool:
        validate_character_ref(character_ref)
        return character_ref in self._entries

    def require_profile(self, character_ref: AttributeSubjectRef) -> CharacterEnergyProfile:
        return self._require(character_ref)[0]

    def require_state(self, character_ref: AttributeSubjectRef) -> EnergyState:
        return self._require(character_ref)[1]

    def current_energy(self, character_ref: AttributeSubjectRef) -> float:
        return self.require_state(character_ref).current_energy

    def assert_can_commit(
        self,
        *,
        operation_id: str,
        expected_version: int,
        expected_energy: Mapping[AttributeSubjectRef, float],
    ) -> None:
        if operation_id in self._committed_operation_ids:
            raise DuplicateEnergyRequestError(f"元素能量 operation 已提交：{operation_id}")
        if expected_version != self._version:
            raise EnergyPlanConflictError(
                f"元素能量 Store 版本冲突：expected={expected_version}, actual={self._version}"
            )
        for ref, value in expected_energy.items():
            if self.current_energy(ref) != value:
                raise EnergyPlanConflictError(f"角色当前元素能量前值冲突：{ref.entity_id}")

    def commit_prevalidated(
        self,
        *,
        operation_id: str,
        new_energy: Mapping[AttributeSubjectRef, float],
    ) -> None:
        for ref, value in new_energy.items():
            profile = self.require_profile(ref)
            if value < 0 or value > profile.capacity:
                raise EnergyPlanConflictError(f"元素能量提交值越界：{ref.entity_id}")
        for ref, value in new_energy.items():
            self.require_state(ref).current_energy = value
        self._version += 1
        self._committed_operation_ids.add(operation_id)

    def _require(
        self, character_ref: AttributeSubjectRef
    ) -> tuple[CharacterEnergyProfile, EnergyState]:
        validate_character_ref(character_ref)
        entry = self._entries.get(character_ref)
        if entry is None:
            raise CharacterEnergyNotFoundError(f"角色元素能量状态不存在：{character_ref.entity_id}")
        return entry
