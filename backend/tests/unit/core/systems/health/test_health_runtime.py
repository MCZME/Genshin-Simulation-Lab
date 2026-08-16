from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.attributes import (
    STAT_HP_BASE,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.entity_states import HealthState
from genshin_sim.core.events import EventEngine, EventType
from genshin_sim.core.systems.health import (
    CharacterDamageApplication,
    CharacterHealingApplication,
    CharacterHealthStore,
    CharacterHpDeduction,
    HealthChangeKind,
    HealthRuntime,
    HealthValidationError,
    InvalidCurrentHealthError,
)

CHARACTER_REF = AttributeSubjectRef.character("character:slot_1")
TARGET_REF = AttributeSubjectRef.target("target:target_1")
SOURCE_REF = AttributeSubjectRef.character("character:slot_2")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.SYSTEM, "test.health")


def _attribute_resolver(max_hp: float = 1000) -> AttributeResolver:
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    CHARACTER_REF,
                    BaseAttributeContribution(STAT_HP_BASE, max_hp, SOURCE_CONTEXT),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _runtime(
    *,
    current_hp: float = 1000,
    max_hp: float = 1000,
) -> tuple[HealthRuntime, HealthState, EventEngine]:
    health = HealthState(current_hp)
    events = EventEngine()
    runtime = HealthRuntime(
        _attribute_resolver(max_hp),
        CharacterHealthStore(((CHARACTER_REF, health),)),
        events,
    )
    return runtime, health, events


def _damage(amount: float, *, change_id: str = "damage:1") -> CharacterDamageApplication:
    return CharacterDamageApplication(
        change_id=change_id,
        frame=1,
        target_ref=CHARACTER_REF,
        amount=amount,
        source_ref=SOURCE_REF,
        source_context=SOURCE_CONTEXT,
    )


def _healing(amount: float, *, change_id: str = "healing:1") -> CharacterHealingApplication:
    return CharacterHealingApplication(
        change_id=change_id,
        frame=1,
        target_ref=CHARACTER_REF,
        amount=amount,
        source_ref=SOURCE_REF,
        source_context=SOURCE_CONTEXT,
    )


def _deduction(
    amount: float,
    *,
    minimum_remaining_hp: float,
    change_id: str = "deduction:1",
) -> CharacterHpDeduction:
    return CharacterHpDeduction(
        change_id=change_id,
        frame=1,
        target_ref=CHARACTER_REF,
        amount=amount,
        minimum_remaining_hp=minimum_remaining_hp,
        source_ref=SOURCE_REF,
        source_context=SOURCE_CONTEXT,
    )


def test_health_runtime_applies_damage_and_publishes_health_changed_event():
    runtime, health, events = _runtime(current_hp=1000)

    result = runtime.apply_damage(_damage(300))

    assert health.current_hp == 700
    assert result.change_kind is HealthChangeKind.DAMAGE
    assert result.effective_amount == 300
    assert result.unapplied_amount == 0
    assert events.frame_events[0].event_type is EventType.CHARACTER_HEALTH_CHANGED
    payload = events.frame_events[0].payload.to_dict()
    assert cast(dict[str, object], payload["result"])["hp_after"] == 700


def test_health_runtime_caps_damage_at_zero_without_defeat_event():
    runtime, health, events = _runtime(current_hp=200)

    result = runtime.apply_damage(_damage(500))

    assert health.current_hp == 0
    assert result.effective_amount == 200
    assert result.unapplied_amount == 300
    assert [event.event_type for event in events.frame_events] == [
        EventType.CHARACTER_HEALTH_CHANGED
    ]


@pytest.mark.parametrize("current_hp, amount", [(0, 500), (1000, 0)])
def test_health_runtime_does_not_publish_event_for_zero_damage_change(
    current_hp: float,
    amount: float,
):
    runtime, health, events = _runtime(current_hp=current_hp)

    result = runtime.apply_damage(_damage(amount))

    assert health.current_hp == current_hp
    assert result.effective_amount == 0
    assert events.frame_events == ()


def test_health_runtime_applies_healing_and_reports_overflow():
    runtime, health, events = _runtime(current_hp=800)

    result = runtime.apply_healing(_healing(500))

    assert health.current_hp == 1000
    assert result.change_kind is HealthChangeKind.HEALING
    assert result.effective_amount == 200
    assert result.unapplied_amount == 300
    assert events.frame_events[0].event_type is EventType.CHARACTER_HEALTH_CHANGED


def test_health_runtime_heals_zero_hp_without_death_state_restriction():
    runtime, health, events = _runtime(current_hp=0)

    result = runtime.apply_healing(_healing(300))

    assert health.current_hp == 300
    assert result.effective_amount == 300
    assert events.frame_events[0].event_type is EventType.CHARACTER_HEALTH_CHANGED


def test_health_runtime_does_not_publish_event_for_full_hp_healing():
    runtime, health, events = _runtime(current_hp=1000)

    result = runtime.apply_healing(_healing(300))

    assert health.current_hp == 1000
    assert result.effective_amount == 0
    assert result.unapplied_amount == 300
    assert events.frame_events == ()


@pytest.mark.parametrize(
    ("minimum_remaining_hp", "expected_hp", "effective", "unapplied"),
    [(0, 0, 200, 300), (1, 1, 199, 301)],
)
def test_health_runtime_deducts_hp_with_explicit_minimum_remaining_hp(
    minimum_remaining_hp: float,
    expected_hp: float,
    effective: float,
    unapplied: float,
):
    runtime, health, events = _runtime(current_hp=200)

    result = runtime.deduct_hp(_deduction(500, minimum_remaining_hp=minimum_remaining_hp))

    assert health.current_hp == expected_hp
    assert result.change_kind is HealthChangeKind.HP_DEDUCTION
    assert result.effective_amount == effective
    assert result.unapplied_amount == unapplied
    assert events.frame_events[0].event_type is EventType.CHARACTER_HEALTH_CHANGED
    payload = events.frame_events[0].payload.to_dict()
    assert cast(dict[str, object], payload["result"])["change_kind"] == "hp_deduction"


def test_health_runtime_does_not_publish_event_when_deduction_is_fully_limited():
    runtime, health, events = _runtime(current_hp=1)

    result = runtime.deduct_hp(_deduction(500, minimum_remaining_hp=1))

    assert health.current_hp == 1
    assert result.effective_amount == 0
    assert result.unapplied_amount == 500
    assert events.frame_events == ()


def test_health_runtime_rejects_invalid_current_hp_without_mutating_or_publishing():
    runtime, health, events = _runtime(current_hp=1200, max_hp=1000)

    with pytest.raises(InvalidCurrentHealthError):
        runtime.apply_damage(_damage(100))

    assert health.current_hp == 1200
    assert events.frame_events == ()


def test_health_runtime_rejects_minimum_remaining_hp_above_max_without_mutating():
    runtime, health, events = _runtime(current_hp=100)

    with pytest.raises(HealthValidationError):
        runtime.deduct_hp(_deduction(10, minimum_remaining_hp=1001))

    assert health.current_hp == 100
    assert events.frame_events == ()


def test_health_runtime_reconciles_dynamic_max_hp_by_ratio_without_health_changed_event():
    runtime, health, events = _runtime(current_hp=500)
    received = []
    events.subscribe(EventType.CHARACTER_MAX_HP_CHANGED, received.append)

    result = runtime.reconcile_max_hp(CHARACTER_REF, old_max_hp=1000, new_max_hp=2000, frame=3)

    assert health.current_hp == 1000
    assert result.hp_before == 500
    assert result.hp_after == 1000
    assert [event.event_type for event in received] == [EventType.CHARACTER_MAX_HP_CHANGED]
    assert [event.event_type for event in events.frame_events] == [
        EventType.CHARACTER_MAX_HP_CHANGED
    ]


def test_health_application_requests_reject_target_subjects():
    with pytest.raises(HealthValidationError):
        CharacterDamageApplication(
            change_id="bad:1",
            frame=1,
            target_ref=TARGET_REF,
            amount=100,
        )
