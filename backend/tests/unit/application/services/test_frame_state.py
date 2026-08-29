"""帧状态投影折叠执行器单元测试。"""

from __future__ import annotations

import pytest

from genshin_sim.application.execution.models import RecordedEvent
from genshin_sim.application.services.frame_state import (
    FRAMES_PER_SECOND,
    coverage_dict,
    fold_frame_state,
)


def _snapshot() -> dict[str, object]:
    return {
        "frame": 0,
        "providers": {
            "team": {
                "frame": 0,
                "active_slot": 1,
                "characters": [
                    {
                        "slot": 1,
                        "character_key": "character:test_a",
                        "combat_entity_id": "character:slot_1",
                        "current_hp": 12000.0,
                        "current_energy": 10.0,
                    },
                    {
                        "slot": 2,
                        "character_key": "character:test_b",
                        "combat_entity_id": "character:slot_2",
                        "current_hp": 9000.0,
                        "current_energy": 0.0,
                    },
                ],
            },
            "attributes": {
                "frame": 0,
                "subjects": {
                    "character:slot_1": {
                        "stat.hp.max": {"value": 15000.0, "applied_terms": []},
                        "stat.atk.total": {"value": 1500.0, "applied_terms": []},
                    },
                    "character:slot_2": {
                        "stat.hp.max": {"value": 13000.0, "applied_terms": []},
                        "stat.atk.total": {"value": 1800.0, "applied_terms": []},
                    },
                },
            },
            "resonance": {"active_keys": ("resonance.pyro",), "team_size": 2},
            "moonsign": {"level": "nascent_gleam", "moonsign_character_refs": ()},
            "aura": {"entities": {}},
            "buff": {"frame": 0, "instances": []},
        },
    }


def _event(ordinal: int, frame: int, event_type: str, data: dict[str, object]) -> RecordedEvent:
    return RecordedEvent(ordinal=ordinal, frame=frame, event_type=event_type, data=data)


def test_baseline_frame_zero_reports_team_attributes_and_coverage():
    response = fold_frame_state(
        session_id="session:1",
        frame=0,
        initial_snapshot=_snapshot(),
        events=(),
    )

    assert response["session_id"] == "session:1"
    assert response["frame"] == 0
    assert response["time_seconds"] == 0.0
    team = response["team"]
    assert team["active_slot"] == 1
    assert team["slots"] == [1, 2]
    assert [item["combat_entity_id"] for item in team["characters"]] == [
        "character:slot_1",
        "character:slot_2",
    ]
    first = response["characters"][0]
    assert first["active"] is True
    assert first["health"] == {"current_hp": 12000.0, "max_hp": 15000.0, "hp_ratio": 0.8}
    assert first["energy"] == {"current_energy": 10.0, "capacity": None, "burst_ready": False}
    assert first["attributes"]["stat.atk.total"] == {"value": 1500.0, "applied_terms": []}
    assert first["buffs"] == []
    assert response["resonance"] == {"active_keys": ["resonance.pyro"]}
    assert response["moonsign"]["level"] == "nascent_gleam"
    assert response["coverage"] == coverage_dict()
    assert set(response["coverage"]) == {
        "team",
        "characters.health",
        "characters.energy",
        "characters.attributes",
        "characters.buffs",
        "characters.shields",
        "characters.infusion",
        "characters.cooldowns",
        "characters.content_states",
        "aura",
        "aura_icd",
        "reaction",
        "space",
    }
    assert response["coverage"]["team"] == "folded"
    assert response["coverage"]["aura"] == "baseline_only"


def test_fold_applies_switch_health_energy_and_attribute_events():
    events = (
        _event(
            0,
            5,
            "TEAM_SWITCHED",
            {"requested_slot": 2, "previous_slot": 1, "active_slot": 2, "accepted": True},
        ),
        _event(
            1,
            6,
            "TEAM_SWITCHED",
            {"requested_slot": 1, "previous_slot": 2, "active_slot": 1, "accepted": False},
        ),
        _event(
            2,
            6,
            "CHARACTER_HEALTH_CHANGED",
            {
                "result": {
                    "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
                    "hp_before": 12000.0,
                    "hp_after": 6000.0,
                    "max_hp": 15000.0,
                }
            },
        ),
        _event(
            3,
            6,
            "CHARACTER_MAX_HP_CHANGED",
            {
                "result": {
                    "target_ref": {"kind": "character", "entity_id": "character:slot_2"},
                    "old_max_hp": 13000.0,
                    "new_max_hp": 19500.0,
                    "hp_before": 9000.0,
                    "hp_after": 13500.0,
                }
            },
        ),
        _event(
            4,
            7,
            "CHARACTER_ENERGY_CHANGED",
            {
                "result": {
                    "target_ref": {"kind": "character", "entity_id": "character:slot_2"},
                    "energy_before": 0.0,
                    "energy_after": 60.0,
                    "capacity": 60.0,
                }
            },
        ),
        _event(
            5,
            7,
            "ATTRIBUTE_PANEL_CHANGED",
            {
                "subject_ref": {"kind": "character", "entity_id": "character:slot_1"},
                "changes": [
                    {
                        "attribute_key": "stat.atk.total",
                        "before_value": 1500.0,
                        "after_value": 2100.0,
                        "after_terms": [{"provider_key": "buff.p", "value": 600.0}],
                    }
                ],
            },
        ),
    )

    response = fold_frame_state(
        session_id="session:1",
        frame=7,
        initial_snapshot=_snapshot(),
        events=events,
    )

    assert response["time_seconds"] == pytest.approx(7 / FRAMES_PER_SECOND)
    assert response["team"]["active_slot"] == 2
    by_slot = {character["slot"]: character for character in response["characters"]}
    assert by_slot[1]["active"] is False
    assert by_slot[1]["health"] == {"current_hp": 6000.0, "max_hp": 15000.0, "hp_ratio": 0.4}
    assert by_slot[1]["attributes"]["stat.atk.total"] == {
        "value": 2100.0,
        "applied_terms": [{"provider_key": "buff.p", "value": 600.0}],
    }
    assert by_slot[2]["health"]["current_hp"] == 13500.0
    assert by_slot[2]["health"]["max_hp"] == 19500.0
    assert by_slot[2]["energy"] == {
        "current_energy": 60.0,
        "capacity": 60.0,
        "burst_ready": True,
    }


def test_fold_ignores_events_after_target_frame():
    events = (
        _event(
            0,
            5,
            "CHARACTER_HEALTH_CHANGED",
            {
                "result": {
                    "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
                    "hp_before": 12000.0,
                    "hp_after": 6000.0,
                    "max_hp": 15000.0,
                }
            },
        ),
        _event(
            1,
            9,
            "CHARACTER_HEALTH_CHANGED",
            {
                "result": {
                    "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
                    "hp_before": 6000.0,
                    "hp_after": 1000.0,
                    "max_hp": 15000.0,
                }
            },
        ),
    )

    response = fold_frame_state(
        session_id="session:1",
        frame=7,
        initial_snapshot=_snapshot(),
        events=events,
    )

    assert response["characters"][0]["health"]["current_hp"] == 6000.0


def test_fold_buffs_shields_infusion_cooldowns_and_content_states():
    buff_instance = {
        "instance_ref": {"domain_key": "buff", "sequence": 1},
        "definition_key": "buff.definition:a",
        "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
        "stack_count": 1,
        "expires_at_frame": 100,
    }
    shield_instance = {
        "instance_ref": {"domain_key": "shield", "sequence": 2},
        "protection_ref": {"kind": "active_team", "protection_id": "team:player"},
        "remaining_native_absorption": 500.0,
        "maximum_native_absorption": 500.0,
        "expires_at_frame": 90,
    }
    infusion_instance = {
        "instance_ref": {"domain_key": "infusion", "sequence": 3},
        "character_ref": {"kind": "character", "entity_id": "character:slot_2"},
        "element": "pyro",
    }
    cooldown_record = {
        "subject_type": "character",
        "subject_id": "character:slot_1",
        "ability_key": "character.test_a.skill",
        "max_charges": 1,
        "available_charges": 0,
        "active_ready_frame": 40,
    }
    events = (
        _event(0, 10, "BUFF_APPLIED", {"result": {"instance_after": buff_instance}}),
        _event(1, 11, "SHIELD_GRANTED", {"result": {"instance_after": shield_instance}}),
        _event(2, 12, "INFUSION_APPLIED", {"result": {"instance_after": infusion_instance}}),
        _event(3, 13, "COOLDOWN_CHANGED", {"after_record": cooldown_record}),
        _event(
            4,
            14,
            "SHIELD_CAPACITY_CHANGED",
            {
                "result": {
                    "instance_ref": {"domain_key": "shield", "sequence": 2},
                    "native_before": 500.0,
                    "native_after": 200.0,
                    "maximum_before": 500.0,
                    "maximum_after": 500.0,
                }
            },
        ),
        _event(
            5,
            15,
            "CONTENT_STATE_CHANGED",
            {
                "owner_ref": "character:slot_1",
                "state_key": "content.test_state",
                "fields": ("level",),
                "before": {"level": 1},
                "after": {"level": 2},
            },
        ),
    )

    response = fold_frame_state(
        session_id="session:1",
        frame=20,
        initial_snapshot=_snapshot(),
        events=events,
    )

    by_slot = {character["slot"]: character for character in response["characters"]}
    assert by_slot[1]["buffs"] == [buff_instance]
    assert by_slot[2]["infusion"] == [infusion_instance]
    assert by_slot[1]["shields"] == [{**shield_instance, "remaining_native_absorption": 200.0}]
    assert by_slot[1]["cooldowns"] == [cooldown_record]
    assert by_slot[1]["content_states"] == [
        {
            "owner_ref": "character:slot_1",
            "state_key": "content.test_state",
            "payload": {"level": 2},
        }
    ]


def test_fold_removes_instances_on_removal_events():
    buff_instance = {
        "instance_ref": {"domain_key": "buff", "sequence": 1},
        "definition_key": "buff.definition:a",
        "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
        "stack_count": 1,
        "expires_at_frame": 100,
    }
    shield_instance = {
        "instance_ref": {"domain_key": "shield", "sequence": 2},
        "protection_ref": {"kind": "character", "protection_id": "character:slot_1"},
        "remaining_native_absorption": 500.0,
        "maximum_native_absorption": 500.0,
        "expires_at_frame": 90,
    }
    events = (
        _event(0, 10, "BUFF_APPLIED", {"result": {"instance_after": buff_instance}}),
        _event(1, 11, "SHIELD_GRANTED", {"result": {"instance_after": shield_instance}}),
        _event(
            2,
            12,
            "BUFF_REMOVED",
            {"result": {"instance_ref": {"domain_key": "buff", "sequence": 1}}},
        ),
        _event(
            3,
            13,
            "SHIELD_REMOVED",
            {"result": {"instance_ref": {"domain_key": "shield", "sequence": 2}}},
        ),
    )

    response = fold_frame_state(
        session_id="session:1",
        frame=13,
        initial_snapshot=_snapshot(),
        events=events,
    )

    assert response["characters"][0]["buffs"] == []
    assert response["characters"][0]["shields"] == []


def test_fold_rejects_snapshot_without_providers():
    with pytest.raises(ValueError, match="providers"):
        fold_frame_state(
            session_id="session:1",
            frame=0,
            initial_snapshot={"frame": 0},
            events=(),
        )
