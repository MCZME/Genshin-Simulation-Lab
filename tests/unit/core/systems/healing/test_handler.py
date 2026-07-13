from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.attributes import (
    STAT_HP_BASE,
    STAT_HP_MAX,
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
from genshin_sim.core.systems.healing import (
    HealingRequest,
    HealingRequestHandler,
    HealingResolver,
    HealingScalingTerm,
    HealingValidationError,
    healing_result_to_application,
)
from genshin_sim.core.systems.health import (
    CharacterHealthStore,
    HealthChangeKind,
    HealthRuntime,
    InvalidCurrentHealthError,
)

SOURCE_REF = AttributeSubjectRef.character("character:slot_1")
TARGET_REF = AttributeSubjectRef.character("character:slot_2")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONTENT, "test.healing")


def _attribute_resolver(
    *,
    source_hp: float = 1000.0,
    target_hp: float = 1000.0,
) -> AttributeResolver:
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    SOURCE_REF,
                    BaseAttributeContribution(STAT_HP_BASE, source_hp, SOURCE_CONTEXT),
                ),
                (
                    TARGET_REF,
                    BaseAttributeContribution(STAT_HP_BASE, target_hp, SOURCE_CONTEXT),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _handler(
    *,
    current_hp: float,
    max_hp: float = 1000.0,
) -> tuple[HealingRequestHandler, HealthState, EventEngine]:
    health = HealthState(current_hp)
    events = EventEngine()
    resolver = _attribute_resolver(target_hp=max_hp)
    health_runtime = HealthRuntime(
        resolver,
        CharacterHealthStore(((TARGET_REF, health),)),
        events,
    )
    handler = HealingRequestHandler(
        HealingResolver(resolver),
        health_runtime,
    )
    return handler, health, events


def _request(
    *,
    scaling_terms: tuple[HealingScalingTerm, ...] | None = None,
    flat_healing: float = 0.0,
) -> HealingRequest:
    if scaling_terms is None:
        scaling_terms = (HealingScalingTerm("hp", STAT_HP_MAX, 0.1),)
    return HealingRequest(
        healing_id="healing:test:1",
        frame=5,
        source_ref=SOURCE_REF,
        target_ref=TARGET_REF,
        scaling_terms=scaling_terms,
        flat_healing=flat_healing,
        source_context=SOURCE_CONTEXT,
        tags=frozenset({"handler"}),
    )


def test_handler_applies_normal_healing_after_publishing_resolved_event():
    handler, health, events = _handler(current_hp=500)

    record = handler.handle(_request())

    assert health.current_hp == 600
    assert record.result.final_healing == 100
    assert record.health_result.change_kind is HealthChangeKind.HEALING
    assert record.health_result.effective_amount == 100
    assert [event.event_type for event in events.frame_events] == [
        EventType.HEALING_RESOLVED,
        EventType.CHARACTER_HEALTH_CHANGED,
    ]
    resolved_payload = events.frame_events[0].payload.to_dict()
    assert cast(dict[str, object], resolved_payload["result"])["final_healing"] == 100
    assert handler.records == (record,)


def test_handler_keeps_theoretical_result_when_health_runtime_reports_overflow():
    handler, health, events = _handler(current_hp=950)

    record = handler.handle(_request())

    assert health.current_hp == 1000
    assert record.result.final_healing == 100
    assert record.health_result.effective_amount == 50
    assert record.health_result.unapplied_amount == 50
    assert [event.event_type for event in events.frame_events] == [
        EventType.HEALING_RESOLVED,
        EventType.CHARACTER_HEALTH_CHANGED,
    ]


def test_handler_publishes_resolved_event_for_full_hp_without_health_changed_event():
    handler, health, events = _handler(current_hp=1000)

    record = handler.handle(_request())

    assert health.current_hp == 1000
    assert record.result.final_healing == 100
    assert record.health_result.effective_amount == 0
    assert record.health_result.unapplied_amount == 100
    assert [event.event_type for event in events.frame_events] == [EventType.HEALING_RESOLVED]


def test_handler_publishes_resolved_event_for_zero_healing_without_health_changed_event():
    handler, health, events = _handler(current_hp=500)

    record = handler.handle(_request(scaling_terms=(), flat_healing=0))

    assert health.current_hp == 500
    assert record.result.final_healing == 0
    assert record.health_result.effective_amount == 0
    assert record.health_result.unapplied_amount == 0
    assert [event.event_type for event in events.frame_events] == [EventType.HEALING_RESOLVED]


def test_handler_keeps_healing_resolved_event_when_health_commit_fails():
    handler, health, events = _handler(current_hp=1200, max_hp=1000)

    with pytest.raises(InvalidCurrentHealthError):
        handler.handle(_request())

    assert health.current_hp == 1200
    assert [event.event_type for event in events.frame_events] == [EventType.HEALING_RESOLVED]
    assert handler.records == ()


def test_handler_rejects_mismatched_event_engine():
    events = EventEngine()
    resolver = _attribute_resolver()
    health_runtime = HealthRuntime(
        resolver,
        CharacterHealthStore(((TARGET_REF, HealthState(500)),)),
        events,
    )

    with pytest.raises(HealingValidationError, match="event_engine"):
        HealingRequestHandler(HealingResolver(resolver), health_runtime, EventEngine())


def test_adapter_converts_healing_result_to_character_healing_application():
    handler, _, _ = _handler(current_hp=500)
    result = handler.resolver.resolve(_request(flat_healing=25))

    application = healing_result_to_application(result)

    assert application.change_id == result.healing_id
    assert application.frame == result.frame
    assert application.target_ref == TARGET_REF
    assert application.amount == result.final_healing
    assert application.source_ref == SOURCE_REF
    assert application.source_context == SOURCE_CONTEXT
    assert application.tags == frozenset({"handler"})
