from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from genshin_sim.analysis.processors.state_fold import (
    StateFoldError,
    fold_state,
)
from tests.helpers.analysis import recorded_event


def _pv(providers: Mapping[str, object], key: str) -> dict[str, object]:
    return cast(dict[str, object], providers[key])


def _baseline() -> dict[str, object]:
    return {
        "providers": {
            "team": {
                "frame": 0,
                "active_slot": 1,
                "characters": [
                    {
                        "slot": 1,
                        "combat_entity_id": "character:slot_1",
                        "current_hp": 10000.0,
                        "current_energy": 0.0,
                    }
                ],
            },
            "cooldown": {
                "schema_version": 1,
                "frame": 0,
                "normalized_through_frame": 0,
                "records": [
                    {
                        "subject_type": "character",
                        "subject_id": "character:slot_1",
                        "ability_key": "elemental_skill",
                        "ability_kind": "skill",
                        "max_charges": 1,
                        "available_charges": 1,
                        "active_started_frame": None,
                        "active_ready_frame": None,
                        "interval_frames": None,
                        "queued_recoveries": 0,
                        "chain_id": None,
                        "revision": 0,
                    }
                ],
            },
            "buff": {"frame": 0, "instances": []},
            "shield": {"frame": 0, "instances": []},
            "infusion": {"frame": 0, "instances": []},
            "attributes": {
                "frame": 0,
                "subjects": {
                    "character:slot_1": {"stat.atk.total": {"value": 1500.0, "applied_terms": []}}
                },
            },
            "aura": {"frame": 0, "records": []},
        }
    }


def _instance_ref(domain_key: str, sequence: int) -> dict[str, object]:
    return {"domain_key": domain_key, "sequence": sequence}


def test_fold_state_applies_team_health_energy_and_attributes():
    events = (
        recorded_event(
            1,
            "TEAM_SWITCHED",
            {
                "requested_slot": 2,
                "previous_slot": 1,
                "active_slot": 2,
                "accepted": True,
                "status": "switched",
            },
        ),
        recorded_event(
            1,
            "CHARACTER_HEALTH_CHANGED",
            {
                "result": {
                    "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
                    "hp_after": 7000.0,
                }
            },
        ),
        recorded_event(
            2,
            "CHARACTER_ENERGY_CHANGED",
            {
                "result": {
                    "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
                    "energy_after": 60.0,
                }
            },
        ),
        recorded_event(
            3,
            "ATTRIBUTE_PANEL_CHANGED",
            {
                "frame": 3,
                "subject_ref": {"kind": "character", "entity_id": "character:slot_1"},
                "changes": [
                    {
                        "attribute_key": "stat.atk.total",
                        "before_value": 1500.0,
                        "after_value": 1800.0,
                        "after_terms": [{"provider_key": "provider:test"}],
                    }
                ],
            },
        ),
    )

    view = fold_state(_baseline(), events, frame=3)

    team = _pv(view.providers, "team")
    assert team["active_slot"] == 2
    character = cast(dict[str, object], cast(list[object], team["characters"])[0])
    assert character["current_hp"] == 7000.0
    assert character["current_energy"] == 60.0
    subjects = cast(dict[str, object], _pv(view.providers, "attributes")["subjects"])
    panel = cast(dict[str, object], subjects["character:slot_1"])
    atk_total = cast(dict[str, object], panel["stat.atk.total"])
    assert atk_total["value"] == 1800.0
    assert atk_total["applied_terms"] == ({"provider_key": "provider:test"},)
    assert view.fold_status["team"] == "folded"
    assert view.fold_status["aura"] == "baseline"


def test_fold_state_filters_events_after_target_frame():
    events = (
        recorded_event(
            1,
            "CHARACTER_HEALTH_CHANGED",
            {
                "result": {
                    "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
                    "hp_after": 9000.0,
                }
            },
        ),
        recorded_event(
            10,
            "CHARACTER_HEALTH_CHANGED",
            {
                "result": {
                    "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
                    "hp_after": 100.0,
                }
            },
        ),
    )

    view = fold_state(_baseline(), events, frame=5)

    team = _pv(view.providers, "team")
    character = cast(dict[str, object], cast(list[object], team["characters"])[0])
    assert character["current_hp"] == 9000.0


def test_fold_state_reduces_cooldown_buff_shield_infusion():
    instance_ref = _instance_ref("buff", 1)
    shield_ref = _instance_ref("shield", 1)
    infusion_ref = _instance_ref("infusion", 1)
    events = (
        recorded_event(
            1,
            "COOLDOWN_CHANGED",
            {
                "subject_ref": {
                    "subject_type": "character",
                    "subject_id": "character:slot_1",
                },
                "ability_key": "elemental_skill",
                "before_available_charges": 1,
                "after_available_charges": 0,
                "active_ready_frame": 150,
                "queued_recoveries": 0,
                "chain_id": "cooldown-chain:test",
            },
        ),
        recorded_event(
            2,
            "BUFF_APPLIED",
            {
                "result": {
                    "instance_ref": instance_ref,
                    "replaced_instance_refs": [],
                    "instance_after": {
                        "instance_ref": instance_ref,
                        "definition_key": "test.buff",
                        "stack_count": 1,
                    },
                }
            },
        ),
        recorded_event(
            3,
            "SHIELD_GRANTED",
            {
                "result": {
                    "instance_ref": shield_ref,
                    "replaced_instance_ref": None,
                    "instance_after": {
                        "instance_ref": shield_ref,
                        "mechanic_key": "test.shield",
                        "remaining_native_absorption": 1000.0,
                    },
                }
            },
        ),
        recorded_event(
            4,
            "SHIELD_CAPACITY_CHANGED",
            {
                "result": {
                    "instance_ref": shield_ref,
                    "native_after": 700.0,
                    "maximum_after": 1000.0,
                }
            },
        ),
        recorded_event(
            5,
            "INFUSION_APPLIED",
            {
                "result": {
                    "instance_ref": infusion_ref,
                    "replaced_instance_refs": [],
                    "instance_after": {
                        "instance_ref": infusion_ref,
                        "definition_key": "test.infusion",
                        "element": "pyro",
                    },
                }
            },
        ),
    )

    view = fold_state(_baseline(), events, frame=5)

    cooldown = _pv(view.providers, "cooldown")
    record = cast(dict[str, object], cast(list[object], cooldown["records"])[0])
    assert record["available_charges"] == 0
    assert record["active_ready_frame"] == 150
    assert record["chain_id"] == "cooldown-chain:test"
    buff_instances = cast(list[dict[str, object]], _pv(view.providers, "buff")["instances"])
    assert buff_instances[0]["definition_key"] == "test.buff"
    shield_instances = cast(list[dict[str, object]], _pv(view.providers, "shield")["instances"])
    assert shield_instances[0]["remaining_native_absorption"] == 700.0
    infusion_instances = cast(list[dict[str, object]], _pv(view.providers, "infusion")["instances"])
    assert infusion_instances[0]["element"] == "pyro"


def test_fold_state_reduces_cooldown_full_after_record():
    events = (
        recorded_event(
            1,
            "COOLDOWN_CHANGED",
            {
                "subject_ref": {
                    "subject_type": "character",
                    "subject_id": "character:slot_1",
                },
                "ability_key": "elemental_skill",
                "before_available_charges": 1,
                "after_available_charges": 0,
                "active_ready_frame": 150,
                "queued_recoveries": 0,
                "chain_id": "cooldown-chain:test",
                "after_record": {
                    "subject_type": "character",
                    "subject_id": "character:slot_1",
                    "ability_key": "elemental_skill",
                    "ability_kind": "skill",
                    "max_charges": 1,
                    "available_charges": 0,
                    "active_started_frame": 10,
                    "active_ready_frame": 150,
                    "interval_frames": 140,
                    "queued_recoveries": 0,
                    "chain_id": "cooldown-chain:test",
                    "revision": 2,
                },
            },
        ),
    )

    view = fold_state(_baseline(), events, frame=1)

    cooldown = _pv(view.providers, "cooldown")
    record = cast(dict[str, object], cast(list[object], cooldown["records"])[0])
    assert record["available_charges"] == 0
    assert record["active_ready_frame"] == 150
    assert record["active_started_frame"] == 10
    assert record["interval_frames"] == 140
    assert record["revision"] == 2
    assert record["chain_id"] == "cooldown-chain:test"


def test_fold_state_reduces_character_max_hp_changed():
    events = (
        recorded_event(
            2,
            "CHARACTER_MAX_HP_CHANGED",
            {
                "result": {
                    "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
                    "hp_after": 12000.0,
                }
            },
        ),
    )

    view = fold_state(_baseline(), events, frame=2)

    team = _pv(view.providers, "team")
    character = cast(dict[str, object], cast(list[object], team["characters"])[0])
    assert character["current_hp"] == 12000.0


def test_fold_state_removes_buff_shield_infusion_instances():
    instance_ref = _instance_ref("buff", 1)
    shield_ref = _instance_ref("shield", 1)
    infusion_ref = _instance_ref("infusion", 1)
    baseline = _baseline()
    baseline_providers = cast(dict[str, object], baseline["providers"])
    cast(dict[str, object], baseline_providers["buff"])["instances"] = [
        {"instance_ref": instance_ref, "definition_key": "test.buff"}
    ]
    cast(dict[str, object], baseline_providers["shield"])["instances"] = [
        {"instance_ref": shield_ref, "mechanic_key": "test.shield"}
    ]
    cast(dict[str, object], baseline_providers["infusion"])["instances"] = [
        {"instance_ref": infusion_ref, "definition_key": "test.infusion"}
    ]
    events = (
        recorded_event(1, "BUFF_REMOVED", {"result": {"instance_ref": instance_ref}}),
        recorded_event(2, "SHIELD_REMOVED", {"result": {"instance_ref": shield_ref}}),
        recorded_event(3, "INFUSION_REMOVED", {"result": {"instance_ref": infusion_ref}}),
    )

    view = fold_state(baseline, events, frame=3)

    assert cast(list[object], _pv(view.providers, "buff")["instances"]) == []
    assert cast(list[object], _pv(view.providers, "shield")["instances"]) == []
    assert cast(list[object], _pv(view.providers, "infusion")["instances"]) == []


def test_fold_state_rejects_missing_instance_after_evidence():
    events = (
        recorded_event(
            1,
            "BUFF_APPLIED",
            {"result": {"instance_ref": _instance_ref("buff", 1), "instance_after": None}},
        ),
    )

    with pytest.raises(StateFoldError, match="instance_after"):
        fold_state(_baseline(), events, frame=1)


def test_fold_state_ignores_unknown_events():
    view = fold_state(
        _baseline(),
        (recorded_event(1, "RESONANCE_ACTIVATED", {"active_keys": []}),),
        frame=1,
    )

    assert view.fold_status["aura"] == "baseline"
