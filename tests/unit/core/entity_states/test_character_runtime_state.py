from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.core.entity_states import CharacterRuntimeState


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


def test_character_runtime_state_tracks_energy_with_controlled_methods():
    character = CharacterRuntimeState(slot=1, character_key="character:75", level=90)

    character.gain_energy(30)
    consumed = character.consume_energy(20)
    failed = character.consume_energy(20)

    assert consumed
    assert not failed
    assert character.energy == 10


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
            {"slot": 1, "character_key": "character:75", "level": 90, "energy": -1},
            "角色能量不能为负数",
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


@pytest.mark.parametrize("method_name", ["gain_energy", "consume_energy"])
def test_character_runtime_state_rejects_negative_energy_amount(method_name: str):
    character = CharacterRuntimeState(slot=1, character_key="character:75", level=90)
    method = getattr(character, method_name)

    with pytest.raises(ValueError, match="数值必须是非负数"):
        method(-1)
