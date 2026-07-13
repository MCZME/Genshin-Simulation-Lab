from __future__ import annotations

from dataclasses import replace

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.core.systems.health import CharacterHpDeduction
from genshin_sim.core.systems.shield import (
    CharacterIncomingDamage,
    ShieldAtomicCommitError,
    ShieldCapacityError,
    ShieldCapacityFormula,
    ShieldComponentUpdate,
    ShieldElement,
    ShieldGrantOutcome,
    ShieldGrantPolicy,
    ShieldRemovalReason,
    ShieldStateConflictError,
    ShieldTargetMismatchError,
)

CHARACTER_A = AttributeSubjectRef.character("character:slot_1")
CHARACTER_B = AttributeSubjectRef.character("character:slot_2")


def _incoming(
    amount: float,
    *,
    damage_id: str = "damage:1",
    frame: int = 2,
    target_ref: AttributeSubjectRef = CHARACTER_A,
    element: DamageElement = DamageElement.PHYSICAL,
) -> CharacterIncomingDamage:
    from genshin_sim.core.systems.shield import ShieldProtectionRef

    return CharacterIncomingDamage(
        damage_id=damage_id,
        frame=frame,
        protection_ref=ShieldProtectionRef.active_team(),
        target_ref=target_ref,
        mitigated_amount=amount,
        element=element,
    )


def test_replace_removes_old_instance_before_granting_new(shield_rig, make_grant):
    first = shield_rig.runtime.grant(make_grant(flat_absorption=1_000))
    shield_rig.event_engine.clear_frame_events()

    second = shield_rig.runtime.grant(make_grant(grant_id="grant:2", frame=2, flat_absorption=600))

    assert second.outcome is ShieldGrantOutcome.REPLACED
    assert second.replaced_instance_id == first.instance_id
    assert second.instance_id != first.instance_id
    assert shield_rig.component_store.require(second.instance_id).remaining_native_absorption == 600
    assert [event.event_type for event in shield_rig.event_engine.frame_events] == [
        EventType.SHIELD_REMOVED,
        EventType.SHIELD_GRANTED,
    ]
    removed = shield_rig.event_engine.frame_events[0].payload.to_dict()["result"]
    assert removed["reason"] == ShieldRemovalReason.REPLACED.value


def test_replace_blocks_reentrant_grant_from_removed_event(shield_rig, make_grant):
    first = shield_rig.runtime.grant(make_grant(flat_absorption=1_000))
    blocked = []

    def try_reenter(event):
        del event
        try:
            shield_rig.runtime.grant(
                make_grant(
                    grant_id="grant:reentrant",
                    frame=2,
                    flat_absorption=200,
                )
            )
        except ShieldStateConflictError:
            blocked.append(True)

    shield_rig.event_engine.subscribe(EventType.SHIELD_REMOVED, try_reenter)
    shield_rig.event_engine.clear_frame_events()

    replacement = shield_rig.runtime.grant(
        make_grant(grant_id="grant:outer", frame=2, flat_absorption=600)
    )

    assert blocked == [True]
    assert replacement.replaced_instance_id == first.instance_id
    assert [component.instance_id for component in shield_rig.component_store.components] == [
        replacement.instance_id
    ]
    assert [event.event_type for event in shield_rig.event_engine.frame_events] == [
        EventType.SHIELD_REMOVED,
        EventType.SHIELD_GRANTED,
    ]


def test_refresh_replace_keeps_identity_and_replaces_capacity(shield_rig, make_grant):
    first = shield_rig.runtime.grant(
        make_grant(
            grant_policy=ShieldGrantPolicy.REFRESH_REPLACE,
            flat_absorption=1_000,
        )
    )
    second = shield_rig.runtime.grant(
        make_grant(
            grant_id="grant:2",
            frame=5,
            duration_frames=20,
            grant_policy=ShieldGrantPolicy.REFRESH_REPLACE,
            flat_absorption=600,
        )
    )

    assert second.instance_id == first.instance_id
    assert second.outcome is ShieldGrantOutcome.REFRESHED
    assert second.remaining_before == 1_000
    assert second.remaining_after == 600
    assert second.expires_at_after == 25


def test_add_capped_refresh_matches_case_g(shield_rig, make_grant):
    first = shield_rig.runtime.grant(
        make_grant(
            grant_policy=ShieldGrantPolicy.ADD_CAPPED_REFRESH,
            flat_absorption=3_000,
            capacity_limit=4_000,
        )
    )
    second = shield_rig.runtime.grant(
        make_grant(
            grant_id="grant:2",
            frame=3,
            grant_policy=ShieldGrantPolicy.ADD_CAPPED_REFRESH,
            flat_absorption=2_000,
            capacity_limit=4_000,
        )
    )

    assert second.instance_id == first.instance_id
    assert second.outcome is ShieldGrantOutcome.STACKED
    assert second.remaining_before == 3_000
    assert second.remaining_after == 4_000
    assert second.maximum_after == 4_000
    assert second.expires_at_after == 63


def test_keep_stronger_refresh_keeps_or_replaces_capacity(shield_rig, make_grant):
    first = shield_rig.runtime.grant(
        make_grant(
            grant_policy=ShieldGrantPolicy.KEEP_STRONGER_REFRESH,
            flat_absorption=1_000,
        )
    )
    kept = shield_rig.runtime.grant(
        make_grant(
            grant_id="grant:2",
            frame=2,
            grant_policy=ShieldGrantPolicy.KEEP_STRONGER_REFRESH,
            flat_absorption=600,
        )
    )
    stronger = shield_rig.runtime.grant(
        make_grant(
            grant_id="grant:3",
            frame=3,
            grant_policy=ShieldGrantPolicy.KEEP_STRONGER_REFRESH,
            flat_absorption=1_500,
        )
    )

    assert kept.instance_id == first.instance_id
    assert kept.outcome is ShieldGrantOutcome.KEPT_EXISTING
    assert kept.remaining_after == 1_000
    assert stronger.outcome is ShieldGrantOutcome.REFRESHED
    assert stronger.remaining_after == 1_500


def test_coexist_allows_different_conflict_keys_and_rejects_same_key(
    shield_rig,
    make_grant,
):
    first = shield_rig.runtime.grant(
        make_grant(
            grant_policy=ShieldGrantPolicy.COEXIST,
            conflict_key="test.shield.a",
        )
    )
    second = shield_rig.runtime.grant(
        make_grant(
            grant_id="grant:2",
            mechanic_key="test.shield.b",
            handler_key="test.shield.b.handler",
            grant_policy=ShieldGrantPolicy.COEXIST,
            conflict_key="test.shield.b",
        )
    )

    assert [item.instance_id for item in shield_rig.component_store.components] == [
        first.instance_id,
        second.instance_id,
    ]
    with pytest.raises(ShieldStateConflictError):
        shield_rig.runtime.grant(
            make_grant(
                grant_id="grant:3",
                frame=3,
                grant_policy=ShieldGrantPolicy.COEXIST,
                conflict_key="test.shield.a",
            )
        )


def test_case_a_overflow_damage_passes_to_health_on_fourth_hit(shield_rig, make_grant):
    grant = shield_rig.runtime.grant(make_grant(flat_absorption=3_500))

    remaining = []
    records = []
    for index in range(4):
        record = shield_rig.runtime.apply_incoming_damage(
            _incoming(
                1_000,
                damage_id=f"damage:{index + 1}",
                frame=index + 2,
            )
        )
        records.append(record)
        component = shield_rig.component_store.get(grant.instance_id)
        remaining.append(None if component is None else component.remaining_native_absorption)

    assert remaining == [2_500, 1_500, 500, None]
    assert [record.shield_result.health_bound_damage for record in records] == [
        0,
        0,
        0,
        500,
    ]
    assert shield_rig.character_a.health.current_hp == 9_500


def test_case_b_same_element_shield_uses_2_5_multiplier(shield_rig, make_grant):
    grant = shield_rig.runtime.grant(make_grant(flat_absorption=1_000, element=ShieldElement.PYRO))

    result = shield_rig.runtime.absorb(_incoming(2_000, element=DamageElement.PYRO))

    assert result.shield_hits[0].element_multiplier == 2.5
    assert result.shield_hits[0].native_cost == 800
    assert shield_rig.component_store.require(grant.instance_id).remaining_native_absorption == 200
    assert result.health_bound_damage == 0


def test_case_c_geo_shield_uses_1_5_for_physical_damage(shield_rig, make_grant):
    grant = shield_rig.runtime.grant(make_grant(flat_absorption=1_000, element=ShieldElement.GEO))

    result = shield_rig.runtime.absorb(_incoming(1_200))

    assert result.shield_hits[0].element_multiplier == 1.5
    assert result.shield_hits[0].native_cost == 800
    assert shield_rig.component_store.require(grant.instance_id).remaining_native_absorption == 200


def test_case_d_dynamic_shield_strength_follows_active_character(
    rig_factory,
    make_grant,
):
    rig = rig_factory(shield_strength_a=0.35, shield_strength_b=0.0)
    grant = rig.runtime.grant(make_grant(flat_absorption=1_000))

    first = rig.runtime.apply_incoming_damage(_incoming(675))
    rig.team_state.switch_to(2, frame=3)
    second = rig.runtime.apply_incoming_damage(
        _incoming(
            600,
            damage_id="damage:2",
            frame=3,
            target_ref=CHARACTER_B,
        )
    )

    assert first.shield_result.active_character_shield_strength == 0.35
    assert first.shield_result.shield_hits[0].native_cost == pytest.approx(500)
    assert (
        rig.component_store.require(grant.instance_id).remaining_native_absorption
        if rig.component_store.get(grant.instance_id) is not None
        else 0
    ) == 0
    assert second.shield_result.active_character_shield_strength == 0
    assert second.shield_result.protected_damage == pytest.approx(500)
    assert second.shield_result.health_bound_damage == pytest.approx(100)
    assert rig.character_b.health.current_hp == 9_900


def test_case_e_multiple_shields_absorb_same_snapshot_without_capacity_sum(
    shield_rig,
    make_grant,
):
    first = shield_rig.runtime.grant(
        make_grant(
            flat_absorption=1_000,
            grant_policy=ShieldGrantPolicy.COEXIST,
            conflict_key="test.shield.a",
        )
    )
    second = shield_rig.runtime.grant(
        make_grant(
            grant_id="grant:2",
            mechanic_key="test.shield.pyro",
            handler_key="test.shield.pyro.handler",
            flat_absorption=600,
            element=ShieldElement.PYRO,
            grant_policy=ShieldGrantPolicy.COEXIST,
            conflict_key="test.shield.b",
        )
    )
    shield_rig.event_engine.clear_frame_events()

    record = shield_rig.runtime.apply_incoming_damage(_incoming(1_700, element=DamageElement.PYRO))

    assert record.shield_result.protected_damage == 1_500
    assert record.shield_result.health_bound_damage == 200
    assert record.shield_result.depleted_instance_ids == (
        first.instance_id,
        second.instance_id,
    )
    assert shield_rig.component_store.components == ()
    assert shield_rig.character_a.health.current_hp == 9_800
    capacity_and_removal = [
        event
        for event in shield_rig.event_engine.frame_events
        if event.event_type in {EventType.SHIELD_CAPACITY_CHANGED, EventType.SHIELD_REMOVED}
    ]
    assert [event.event_type for event in capacity_and_removal] == [
        EventType.SHIELD_CAPACITY_CHANGED,
        EventType.SHIELD_CAPACITY_CHANGED,
        EventType.SHIELD_REMOVED,
        EventType.SHIELD_REMOVED,
    ]
    assert [event.payload.to_dict()["result"]["instance_id"] for event in capacity_and_removal] == [
        first.instance_id,
        second.instance_id,
        first.instance_id,
        second.instance_id,
    ]


def test_case_f_input_amount_is_already_mitigated_before_shield(shield_rig, make_grant):
    shield_rig.runtime.grant(make_grant(flat_absorption=1_000))

    record = shield_rig.runtime.apply_incoming_damage(
        _incoming(1_000, damage_id="mitigated:from_2000_at_50_percent")
    )

    assert record.incoming_damage.mitigated_amount == 1_000
    assert record.shield_result.health_bound_damage == 0
    assert shield_rig.character_a.health.current_hp == 10_000


def test_case_h_expired_shield_does_not_participate_at_expiry_frame(
    shield_rig,
    make_grant,
):
    grant = shield_rig.runtime.grant(
        make_grant(frame=10, duration_frames=60, flat_absorption=1_000)
    )
    assert shield_rig.mechanic_runtime.instance_store.require(grant.instance_id).is_active_at(69)

    shield_rig.mechanic_runtime.update_frame(None, 70)
    record = shield_rig.runtime.apply_incoming_damage(
        _incoming(500, damage_id="damage:expiry", frame=70)
    )

    assert record.shield_result.had_active_shield_before is False
    assert record.shield_result.health_bound_damage == 500
    assert shield_rig.character_a.health.current_hp == 9_500


def test_no_shield_and_zero_damage_form_complete_application_records(
    shield_rig,
    make_grant,
):
    no_shield = shield_rig.runtime.apply_incoming_damage(_incoming(250))
    assert no_shield.shield_result.shield_hits == ()
    assert no_shield.health_result.effective_amount == 250

    grant = shield_rig.runtime.grant(
        make_grant(grant_id="grant:zero", frame=3, flat_absorption=1_000)
    )
    shield_rig.event_engine.clear_frame_events()
    zero = shield_rig.runtime.apply_incoming_damage(_incoming(0, damage_id="damage:zero", frame=4))

    assert zero.health_result.effective_amount == 0
    assert (
        shield_rig.component_store.require(grant.instance_id).remaining_native_absorption == 1_000
    )
    assert [event.event_type for event in shield_rig.event_engine.frame_events] == [
        EventType.DAMAGE_APPLIED
    ]


def test_fully_absorbed_damage_event_order_has_no_fake_health_change(
    shield_rig,
    make_grant,
):
    shield_rig.runtime.grant(make_grant(flat_absorption=1_000))
    shield_rig.event_engine.clear_frame_events()

    record = shield_rig.runtime.apply_incoming_damage(_incoming(500))

    assert record.health_application.amount == 0
    assert record.health_result.effective_amount == 0
    assert [event.event_type for event in shield_rig.event_engine.frame_events] == [
        EventType.SHIELD_CAPACITY_CHANGED,
        EventType.SHIELD_ABSORPTION_RESOLVED,
        EventType.DAMAGE_APPLIED,
    ]
    assert EventType.CHARACTER_HEALTH_CHANGED not in {
        event.event_type for event in shield_rig.event_engine.frame_events
    }


def test_same_protection_ref_reentrant_absorption_is_blocked(
    shield_rig,
    make_grant,
):
    shield_rig.runtime.grant(make_grant(flat_absorption=1_000))
    blocked = []

    def try_reenter(event):
        del event
        try:
            shield_rig.runtime.absorb(_incoming(1, damage_id="damage:reentrant"))
        except ShieldStateConflictError:
            blocked.append(True)

    shield_rig.event_engine.subscribe(EventType.SHIELD_CAPACITY_CHANGED, try_reenter)

    shield_rig.runtime.absorb(_incoming(100))

    assert blocked == [True]


def test_batch_commit_version_conflict_has_no_partial_state_change(
    shield_rig,
    make_grant,
):
    first = shield_rig.runtime.grant(
        make_grant(
            flat_absorption=1_000,
            grant_policy=ShieldGrantPolicy.COEXIST,
            conflict_key="test.a",
        )
    )
    second = shield_rig.runtime.grant(
        make_grant(
            grant_id="grant:2",
            mechanic_key="test.b",
            handler_key="test.b.handler",
            flat_absorption=600,
            grant_policy=ShieldGrantPolicy.COEXIST,
            conflict_key="test.b",
        )
    )
    version = shield_rig.component_store.version
    updates = (
        ShieldComponentUpdate(first.instance_id, 1_000, 900, 1_000),
        ShieldComponentUpdate(second.instance_id, 600, 500, 600),
    )

    with pytest.raises(ShieldAtomicCommitError):
        shield_rig.component_store.apply_batch(
            updates,
            expected_version=version - 1,
        )

    assert [
        component.remaining_native_absorption for component in shield_rig.component_store.components
    ] == [1_000, 600]


def test_batch_commit_missing_component_has_no_partial_state_change(
    shield_rig,
    make_grant,
):
    grant = shield_rig.runtime.grant(make_grant(flat_absorption=1_000))
    version = shield_rig.component_store.version

    with pytest.raises(ShieldAtomicCommitError):
        shield_rig.component_store.apply_batch(
            (
                ShieldComponentUpdate(grant.instance_id, 1_000, 900, 1_000),
                ShieldComponentUpdate(999, 100, 50, 100),
            ),
            expected_version=version,
        )

    assert (
        shield_rig.component_store.require(grant.instance_id).remaining_native_absorption == 1_000
    )


def test_invalid_dynamic_strength_does_not_change_any_shield(
    rig_factory,
    make_grant,
):
    rig = rig_factory(shield_strength_a=-1.0)
    first = rig.runtime.grant(
        make_grant(
            flat_absorption=1_000,
            grant_policy=ShieldGrantPolicy.COEXIST,
            conflict_key="test.a",
        )
    )
    second = rig.runtime.grant(
        make_grant(
            grant_id="grant:2",
            mechanic_key="test.b",
            handler_key="test.b.handler",
            flat_absorption=600,
            grant_policy=ShieldGrantPolicy.COEXIST,
            conflict_key="test.b",
        )
    )

    with pytest.raises(ShieldCapacityError):
        rig.runtime.apply_incoming_damage(_incoming(500))

    assert rig.component_store.require(first.instance_id).remaining_native_absorption == 1_000
    assert rig.component_store.require(second.instance_id).remaining_native_absorption == 600
    assert rig.character_a.health.current_hp == 10_000


def test_active_team_rejects_background_character_target(shield_rig, make_grant):
    shield_rig.runtime.grant(make_grant())

    with pytest.raises(ShieldTargetMismatchError):
        shield_rig.runtime.absorb(_incoming(100, target_ref=CHARACTER_B))


@pytest.mark.parametrize(
    "reason",
    [ShieldRemovalReason.DISPELLED, ShieldRemovalReason.OWNER_REMOVED],
)
def test_explicit_removal_publishes_requested_reason(
    shield_rig,
    make_grant,
    reason,
):
    grant = shield_rig.runtime.grant(make_grant())
    shield_rig.event_engine.clear_frame_events()

    result = shield_rig.runtime.remove(grant.instance_id, frame=2, reason=reason)

    assert result.reason is reason
    assert shield_rig.component_store.get(grant.instance_id) is None
    assert (
        shield_rig.event_engine.frame_events[0].payload.to_dict()["result"]["reason"]
        == reason.value
    )


def test_hp_deduction_bypasses_active_shield(shield_rig, make_grant):
    grant = shield_rig.runtime.grant(make_grant(flat_absorption=1_000))

    result = shield_rig.health_runtime.deduct_hp(
        CharacterHpDeduction(
            change_id="deduction:1",
            frame=2,
            target_ref=CHARACTER_A,
            amount=100,
            minimum_remaining_hp=0,
        )
    )

    assert result.effective_amount == 100
    assert shield_rig.character_a.health.current_hp == 9_900
    assert (
        shield_rig.component_store.require(grant.instance_id).remaining_native_absorption == 1_000
    )


def test_failed_grant_does_not_modify_old_instance_or_publish_events(
    shield_rig,
    make_grant,
):
    first = shield_rig.runtime.grant(make_grant(flat_absorption=1_000))
    shield_rig.event_engine.clear_frame_events()
    invalid = replace(
        make_grant(grant_id="grant:invalid", frame=2),
        grant_formula=ShieldCapacityFormula(flat_absorption=0),
    )

    with pytest.raises(ShieldCapacityError):
        shield_rig.runtime.grant(invalid)

    assert (
        shield_rig.component_store.require(first.instance_id).remaining_native_absorption == 1_000
    )
    assert shield_rig.event_engine.frame_events == ()
