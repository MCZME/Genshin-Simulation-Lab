from __future__ import annotations

from types import SimpleNamespace

from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.core.systems.shield import (
    CharacterIncomingDamage,
    ShieldImpactRequestHandler,
    ShieldProtectionRef,
)


def test_shield_impact_handler_adapts_free_mapping_once(shield_rig):
    handler = ShieldImpactRequestHandler(shield_rig.runtime)
    context = SimpleNamespace(space_runtime=SimpleNamespace(team_state=shield_rig.team_state))
    request = ImpactRequest(
        frame=5,
        kind=ImpactKind.SHIELD,
        impact_key="test.shield.impact",
        owner_slot=1,
        action_key="test.shield.action",
        request_id="grant:impact",
        source_impact_point_id="impact-point:1",
        element="pyro",
        params={
            "shield": {
                "mechanic_key": "test.shield.from_impact",
                "handler_key": "test.shield.handler",
                "conflict_key": "test.shield.conflict",
                "duration_frames": 60,
                "grant_policy": "replace",
                "grant_formula": {
                    "scaling_terms": (
                        {
                            "component_key": "hp",
                            "attribute_key": "stat.hp.max",
                            "coefficient": 0.1,
                        },
                    ),
                    "flat_absorption": 100,
                    "native_multipliers": ({"multiplier_key": "mode", "multiplier": 1.2},),
                },
                "tags": ("testing.shield",),
            }
        },
    )

    result = handler.handle_impact_request(context, request)

    assert result.resolution.granted_absorption == 1_320
    assert result.resolution.creator_ref.entity_id == "character:slot_1"
    assert handler.records[0].grant_request.grant_formula.scaling_terms[0].component_key == "hp"
    assert (
        shield_rig.component_store.require(result.instance_id).remaining_native_absorption == 1_320
    )


def test_shield_snapshot_keeps_native_capacity_and_stable_refs(
    shield_rig,
    make_grant,
):
    grant = shield_rig.runtime.grant(make_grant(flat_absorption=1_000))
    shield_rig.runtime.absorb(
        CharacterIncomingDamage(
            damage_id="damage:1",
            frame=2,
            protection_ref=ShieldProtectionRef.active_team(),
            target_ref=grant.resolution.creator_ref,
            mitigated_amount=250,
            element=DamageElement.PHYSICAL,
        )
    )

    snapshot = shield_rig.runtime.snapshot(2)

    assert len(snapshot.instances) == 1
    instance = snapshot.instances[0]
    assert instance.instance_id == grant.instance_id
    assert instance.maximum_native_absorption == 1_000
    assert instance.remaining_native_absorption == 750
    assert instance.created_frame == 1
    assert instance.expires_at_frame == 61
    assert snapshot.to_dict()["instances"][0]["protection_ref"] == {
        "kind": "active_team",
        "protection_id": "team:player",
    }
