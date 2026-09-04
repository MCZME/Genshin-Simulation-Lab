from __future__ import annotations

import pytest

from genshin_sim.core.entity_states import CharacterRuntimeState
from genshin_sim.core.simulation import TeamRuntimeState, TeamSwitchStatus


def _character(slot: int, *, combat_entity_id: str = "") -> CharacterRuntimeState:
    return CharacterRuntimeState(
        slot=slot,
        character_key=f"character:{slot}",
        level=90,
        combat_entity_id=combat_entity_id,
    )


def _team_state(size: int = 4, *, active_slot: int = 1) -> TeamRuntimeState:
    return TeamRuntimeState(
        (_character(slot) for slot in range(1, size + 1)),
        active_slot=active_slot,
    )


def test_team_runtime_state_switches_with_one_based_slots():
    team_state = _team_state(size=4, active_slot=1)

    switched = team_state.switch_to(3, frame=10)

    assert switched.accepted
    assert switched.status is TeamSwitchStatus.SWITCHED
    assert switched.previous_slot == 1
    assert switched.active_slot == 3
    assert team_state.active_slot == 3

    same_slot = team_state.switch_to(3, frame=11)

    assert not same_slot.accepted
    assert same_slot.status is TeamSwitchStatus.SAME_SLOT
    assert team_state.active_slot == 3

    invalid_slot = team_state.switch_to(5, frame=12)

    assert not invalid_slot.accepted
    assert invalid_slot.status is TeamSwitchStatus.INVALID_SLOT
    assert team_state.active_slot == 3


def test_team_runtime_state_exposes_current_character():
    team_state = _team_state(size=3, active_slot=2)

    assert team_state.team_size == 3
    assert team_state.slots == (1, 2, 3)
    assert team_state.current_character.slot == 2
    assert team_state.get_character(3) is not None
    assert team_state.get_character(4) is None

    team_state.switch_to(3, frame=1)

    assert team_state.current_character.slot == 3


@pytest.mark.parametrize(
    ("characters", "active_slot", "message"),
    [
        ([], 1, "队伍至少需要一个角色运行态"),
        ([_character(slot) for slot in range(1, 6)], 1, "队伍角色数量必须在 1 到 4 之间"),
        ([_character(1), _character(1)], 1, "队伍槽位重复：1"),
        ([_character(1), _character(3)], 1, "队伍槽位必须从 1 开始连续排列"),
        (
            [_character(1, combat_entity_id="same"), _character(2, combat_entity_id="same")],
            1,
            "角色战斗实体 id 不能重复",
        ),
        ([_character(1), _character(2)], 3, "当前场上槽位必须在队伍槽位范围内"),
    ],
)
def test_team_runtime_state_validates_slots(
    characters: list[CharacterRuntimeState],
    active_slot: int,
    message: str,
):
    with pytest.raises(ValueError, match=message):
        TeamRuntimeState(characters, active_slot=active_slot)
