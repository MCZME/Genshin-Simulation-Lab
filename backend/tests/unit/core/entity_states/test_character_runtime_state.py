from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    ContentStateMount,
    EnergyState,
)


def test_character_runtime_state_builds_default_combat_entity_id_and_copies_talents():
    talents = {"normal_attack": 1}

    character = CharacterRuntimeState(
        slot=2,
        character_key="character:75",
        level=90,
        constellation=2,
        talent_levels=talents,
    )
    talents["normal_attack"] = 10

    assert character.combat_entity_id == "character:slot_2"
    assert character.talent_levels == {"normal_attack": 1}


def test_character_runtime_state_owns_energy_state_without_direct_write_methods():
    character = CharacterRuntimeState(slot=1, character_key="character:75", level=90)

    assert isinstance(character.energy, EnergyState)
    assert character.energy.current_energy == 0.0
    assert not hasattr(character, "gain_energy")
    assert not hasattr(character, "consume_energy")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"slot": 0, "character_key": "character:75", "level": 90}, "角色槽位必须是正整数"),
        ({"slot": 1, "character_key": "", "level": 90}, "角色 asset_key 必须是非空字符串"),
        ({"slot": 1, "character_key": "character:75", "level": 0}, "角色等级必须是正整数"),
        (
            {"slot": 1, "character_key": "character:75", "level": 90, "constellation": 7},
            "角色命座必须在 0 到 6 之间",
        ),
        (
            {"slot": 1, "character_key": "character:75", "level": 90, "energy": 1},
            "角色元素能量状态必须是 EnergyState",
        ),
        (
            {
                "slot": 1,
                "character_key": "character:75",
                "level": 90,
                "talent_levels": {"normal_attack": 0},
            },
            "角色天赋等级必须是正整数",
        ),
    ],
)
def test_character_runtime_state_validates_minimum_fields(
    kwargs: dict[str, object],
    message: str,
):
    with pytest.raises(ValueError, match=message):
        CharacterRuntimeState(**cast(Any, kwargs))


def test_character_runtime_state_rejects_invalid_energy_state():
    with pytest.raises(ValueError, match="角色元素能量状态必须是 EnergyState"):
        CharacterRuntimeState(slot=1, character_key="character:75", level=90, energy=cast(Any, 1))


def _content_state_mount(owner_ref: str, state_key: str = "character.test") -> ContentStateMount:
    return ContentStateMount(
        state_key=state_key,
        schema=StateSchema(
            owner_ref=owner_ref,
            fields=(
                StateField(
                    name="stacks",
                    field_type=StateFieldType.INT,
                    default=0,
                ),
            ),
        ),
    )


def test_character_runtime_state_mounts_content_states_by_state_key():
    mount = _content_state_mount("character:slot_1")

    character = CharacterRuntimeState(
        slot=1,
        character_key="character:75",
        level=90,
        content_states={"character.test": mount},
    )

    assert character.content_states == {"character.test": mount}
    assert character.content_states["character.test"].owner == "character:slot_1"


def test_character_runtime_state_rejects_content_state_owner_mismatch():
    mount = _content_state_mount("character:slot_2")

    with pytest.raises(ValueError, match="必须等于角色实体"):
        CharacterRuntimeState(
            slot=1,
            character_key="character:75",
            level=90,
            content_states={"character.test": mount},
        )


def test_character_runtime_state_rejects_content_state_key_mismatch():
    mount = _content_state_mount("character:slot_1")

    with pytest.raises(ValueError, match="必须与挂载 state_key 一致"):
        CharacterRuntimeState(
            slot=1,
            character_key="character:75",
            level=90,
            content_states={"character.other": mount},
        )


def test_character_runtime_state_rejects_non_mount_content_state():
    with pytest.raises(ValueError, match="必须是 ContentStateMount"):
        CharacterRuntimeState(
            slot=1,
            character_key="character:75",
            level=90,
            content_states=cast(Any, {"character.test": object()}),
        )
