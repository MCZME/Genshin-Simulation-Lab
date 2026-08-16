from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from genshin_sim.core.entity_states import CharacterRuntimeState


class TeamSwitchStatus(StrEnum):
    """队伍切换请求的最小结果状态。"""

    SWITCHED = "switched"
    SAME_SLOT = "same_slot"
    INVALID_SLOT = "invalid_slot"
    BUSY = "busy"


@dataclass(frozen=True, slots=True)
class TeamSwitchResult:
    """一次切换槽位请求的结果。"""

    frame: int
    requested_slot: int
    previous_slot: int
    active_slot: int
    status: TeamSwitchStatus

    @property
    def accepted(self) -> bool:
        return self.status is TeamSwitchStatus.SWITCHED


class TeamRuntimeState:
    """队伍运行态的最小骨架。

    槽位使用 1-based 编号，与 `keyboard.1` ~ `keyboard.4` 保持一致。
    """

    __slots__ = ("_characters", "active_slot")

    def __init__(
        self,
        characters: Iterable[CharacterRuntimeState],
        *,
        active_slot: int = 1,
    ) -> None:
        character_list = tuple(characters)
        if not character_list:
            msg = "队伍至少需要一个角色运行态"
            raise ValueError(msg)
        if len(character_list) > 4:
            msg = "队伍角色数量必须在 1 到 4 之间"
            raise ValueError(msg)

        character_by_slot: dict[int, CharacterRuntimeState] = {}
        for character in character_list:
            if character.slot in character_by_slot:
                msg = f"队伍槽位重复：{character.slot}"
                raise ValueError(msg)
            character_by_slot[character.slot] = character

        slots = sorted(character_by_slot)
        if slots != list(range(1, len(character_by_slot) + 1)):
            msg = "队伍槽位必须从 1 开始连续排列"
            raise ValueError(msg)

        combat_entity_ids = [character.combat_entity_id for character in character_list]
        if len(combat_entity_ids) != len(set(combat_entity_ids)):
            msg = "角色战斗实体 id 不能重复"
            raise ValueError(msg)

        if active_slot not in character_by_slot:
            msg = "当前场上槽位必须在队伍槽位范围内"
            raise ValueError(msg)

        self._characters = character_by_slot
        self.active_slot = active_slot

    @property
    def team_size(self) -> int:
        return len(self._characters)

    @property
    def slots(self) -> tuple[int, ...]:
        return tuple(sorted(self._characters))

    @property
    def characters(self) -> tuple[CharacterRuntimeState, ...]:
        return tuple(self._characters[slot] for slot in self.slots)

    @property
    def current_character(self) -> CharacterRuntimeState:
        return self._characters[self.active_slot]

    def get_character(self, slot: int) -> CharacterRuntimeState | None:
        return self._characters.get(slot)

    def switch_to(self, slot: int, frame: int) -> TeamSwitchResult:
        previous_slot = self.active_slot

        if slot not in self._characters:
            return TeamSwitchResult(
                frame=frame,
                requested_slot=slot,
                previous_slot=previous_slot,
                active_slot=self.active_slot,
                status=TeamSwitchStatus.INVALID_SLOT,
            )

        if slot == self.active_slot:
            return TeamSwitchResult(
                frame=frame,
                requested_slot=slot,
                previous_slot=previous_slot,
                active_slot=self.active_slot,
                status=TeamSwitchStatus.SAME_SLOT,
            )

        self.active_slot = slot
        return TeamSwitchResult(
            frame=frame,
            requested_slot=slot,
            previous_slot=previous_slot,
            active_slot=self.active_slot,
            status=TeamSwitchStatus.SWITCHED,
        )
