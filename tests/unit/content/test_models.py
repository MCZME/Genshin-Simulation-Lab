from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from genshin_sim.content import (
    ContentRuntimeContribution,
    ContentStateSlotError,
    ContentStateSnapshot,
    ContentStateStore,
    ContentStateTypeError,
    HookResult,
)


@dataclass(frozen=True, slots=True)
class FurinaState:
    fanfare: int


@dataclass(frozen=True, slots=True)
class OtherState:
    active: bool


def test_character_state_store_sets_and_gets_typed_state():
    store = ContentStateStore()
    state = FurinaState(fanfare=42)

    store.set_character_state(
        slot=1,
        handler_key="character.furina",
        state=state,
    )

    assert (
        store.get_character_state(
            slot=1,
            handler_key="character.furina",
            expected_type=FurinaState,
        )
        is state
    )


def test_character_state_store_rejects_missing_slot():
    store = ContentStateStore()

    with pytest.raises(ContentStateSlotError, match="需要 slot"):
        store.set_character_state(
            slot=None,
            handler_key="character.furina",
            state=FurinaState(fanfare=0),
        )


def test_character_state_store_reports_type_mismatch():
    store = ContentStateStore()
    store.set_character_state(
        slot=1,
        handler_key="character.furina",
        state=FurinaState(fanfare=42),
    )

    with pytest.raises(ContentStateTypeError, match="期望 OtherState，实际 FurinaState"):
        store.get_character_state(
            slot=1,
            handler_key="character.furina",
            expected_type=OtherState,
        )


def test_content_state_store_supports_non_character_owner_states():
    store = ContentStateStore()
    weapon_state = OtherState(active=True)
    artifact_state = {"pieces": 4}
    generic_state = {"enabled": True}

    store.set_weapon_state(slot=1, handler_key="weapon.test", state=weapon_state)
    store.set_artifact_state(slot=1, handler_key="artifact.test", state=artifact_state)
    store.set_generic_state(
        owner_ref="impact:effect:char",
        handler_key="impact.test",
        state=generic_state,
    )

    assert (
        store.get_weapon_state(
            slot=1,
            handler_key="weapon.test",
            expected_type=OtherState,
        )
        is weapon_state
    )
    assert store.get_artifact_state(slot=1, handler_key="artifact.test") == artifact_state
    assert (
        store.get_generic_state(
            owner_ref="impact:effect:char",
            handler_key="impact.test",
        )
        == generic_state
    )


def test_content_runtime_contribution_normalizes_factory_mappings():
    impact_factory = object()
    created_object_behavior = object()

    contribution = ContentRuntimeContribution(
        owner_type="character",
        owner_key="character:75",
        handler_key="character.test",
        slot=1,
        impact_factories={"impact.test": impact_factory},
        created_object_behaviors={"created_object.test": created_object_behavior},
    )

    assert contribution.impact_factories == {"impact.test": impact_factory}
    assert contribution.created_object_behaviors == {"created_object.test": created_object_behavior}


def test_content_state_snapshot_accepts_json_compatible_payload():
    payload = {
        "fanfare": 42,
        "members": ["gentilhomme", "surintendante"],
        "flags": {"arkhe": "ousia", "active": True, "cooldown": None},
    }

    snapshot = ContentStateSnapshot(
        owner_ref="character:slot:1",
        handler_key="character.furina",
        schema_version=1,
        frame=120,
        payload=payload,
    )

    assert snapshot.payload == payload


def test_content_state_snapshot_rejects_non_json_payload():
    payload: Any = {"bad": (1, 2)}

    with pytest.raises(TypeError, match="payload.bad"):
        ContentStateSnapshot(
            owner_ref="character:slot:1",
            handler_key="character.furina",
            schema_version=1,
            frame=120,
            payload=payload,
        )


def test_hook_result_basic_construction():
    hook_result = HookResult(
        impact_requests=["impact.request"],
        modifier_commands=[{"command": "add"}],
        state_patches=[{"path": ["fanfare"], "value": 43}],
        audit_notes=["triggered"],
    )

    assert hook_result.impact_requests == ("impact.request",)
    assert hook_result.modifier_commands == ({"command": "add"},)
    assert hook_result.state_patches == ({"path": ["fanfare"], "value": 43},)
    assert hook_result.audit_notes == ("triggered",)


def test_content_runtime_contribution_freezes_attribute_extensions():
    contribution = ContentRuntimeContribution(
        owner_type="character",
        owner_key="character:1",
        handler_key="character.test",
        attribute_definitions=[],
        attribute_providers=[],
    )

    assert contribution.attribute_definitions == ()
    assert contribution.attribute_providers == ()
