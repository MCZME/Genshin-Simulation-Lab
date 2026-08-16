from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.content import (
    ContentStateSnapshot,
    HookResult,
)


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
