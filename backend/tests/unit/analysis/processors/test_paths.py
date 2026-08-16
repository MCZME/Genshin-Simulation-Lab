from __future__ import annotations

import pytest

from genshin_sim.analysis.processors.paths import (
    StatePathError,
    parse_state_path,
    resolve_state_path,
)


def _team_data() -> dict[str, object]:
    return {
        "team": {
            "active_slot": 1,
            "characters": [
                {"slot": 1, "combat_entity_id": "character:slot_1", "current_hp": 7000.0},
                {"slot": 2, "combat_entity_id": "character:slot_2", "current_hp": 9000.0},
            ],
        },
        "attributes": {
            "subjects": {
                "character:slot_1": {"stat.atk.total": {"value": 1800.0, "applied_terms": []}}
            }
        },
    }


def test_parse_and_resolve_field_path():
    data = _team_data()

    assert resolve_state_path(data, "team.active_slot") == 1
    assert resolve_state_path(data, "team.characters[slot=1].current_hp") == 7000.0
    assert (
        resolve_state_path(data, "team.characters[combat_entity_id=character:slot_2].current_hp")
        == 9000.0
    )


def test_resolve_path_returns_node():
    data = _team_data()

    character = resolve_state_path(data, "team.characters[slot=1]")

    assert character == ({"slot": 1, "combat_entity_id": "character:slot_1", "current_hp": 7000.0},)


def test_resolve_path_supports_quoted_keys_with_special_characters():
    data = _team_data()

    atk_total = resolve_state_path(
        data,
        'attributes.subjects["character:slot_1"]["stat.atk.total"]',
    )

    assert atk_total == {"value": 1800.0, "applied_terms": []}


def test_filter_returns_all_matches_as_terminal_node():
    data = _team_data()

    characters = resolve_state_path(data, "team.characters[combat_entity_id=character:slot_1]")

    assert characters == (
        {"slot": 1, "combat_entity_id": "character:slot_1", "current_hp": 7000.0},
    )


def test_resolve_path_raises_for_missing_key():
    with pytest.raises(StatePathError, match="路径键不存在"):
        resolve_state_path(_team_data(), "team.missing")


def test_resolve_path_raises_when_filter_is_ambiguous_in_middle():
    data = _team_data()

    with pytest.raises(StatePathError, match="匹配 0 项"):
        resolve_state_path(data, "team.characters[slot=9].current_hp")


def test_parse_state_path_rejects_invalid_segments():
    with pytest.raises(StatePathError, match="非法筛选段"):
        parse_state_path("team.characters[]")
    with pytest.raises(StatePathError, match="非空字符串"):
        parse_state_path("")
    with pytest.raises(StatePathError, match="非法路径"):
        parse_state_path("team..characters")
