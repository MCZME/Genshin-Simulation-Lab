"""月兆领域状态的唯一真值来源。"""

from __future__ import annotations

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.moonsign.errors import MoonsignStateConflictError
from genshin_sim.core.systems.moonsign.models import (
    MoonsignBonusRecord,
    MoonsignLevel,
)


class MoonsignStore:
    """保存月兆等级、月兆角色集合与当前非月兆月曜增伤记录。"""

    def __init__(self) -> None:
        self._level = MoonsignLevel.NONE
        self._moonsign_character_refs: tuple[AttributeSubjectRef, ...] = ()
        self._bonus: MoonsignBonusRecord | None = None
        self._version = 0
        self._level_initialized = False

    @property
    def level(self) -> MoonsignLevel:
        return self._level

    @property
    def moonsign_character_refs(self) -> tuple[AttributeSubjectRef, ...]:
        return self._moonsign_character_refs

    @property
    def bonus(self) -> MoonsignBonusRecord | None:
        return self._bonus

    @property
    def version(self) -> int:
        return self._version

    def set_level(
        self,
        level: MoonsignLevel,
        moonsign_character_refs: tuple[AttributeSubjectRef, ...],
    ) -> None:
        if self._level_initialized:
            raise MoonsignStateConflictError("月兆等级只能在组装期设置一次")
        if not isinstance(level, MoonsignLevel):
            raise MoonsignStateConflictError("月兆等级必须是 MoonsignLevel")
        raw_refs = tuple(moonsign_character_refs)
        if any(not isinstance(ref, AttributeSubjectRef) for ref in raw_refs):
            raise MoonsignStateConflictError("月兆角色引用必须是 AttributeSubjectRef")
        refs = tuple(
            sorted(
                {ref for ref in raw_refs},
                key=lambda item: (item.kind.value, item.entity_id),
            )
        )
        self._level = level
        self._moonsign_character_refs = refs
        self._level_initialized = True
        self._version += 1

    def apply_bonus(self, record: MoonsignBonusRecord) -> None:
        if not isinstance(record, MoonsignBonusRecord):
            raise MoonsignStateConflictError("月曜增伤记录必须是 MoonsignBonusRecord")
        self._bonus = record
        self._version += 1

    def clear_expired(self, frame: int) -> MoonsignBonusRecord | None:
        if self._bonus is None or self._bonus.is_active_at(frame):
            return None
        expired = self._bonus
        self._bonus = None
        self._version += 1
        return expired

    def current_bonus_value(self, frame: int) -> float:
        if self._bonus is None or not self._bonus.is_active_at(frame):
            return 0.0
        return self._bonus.value
