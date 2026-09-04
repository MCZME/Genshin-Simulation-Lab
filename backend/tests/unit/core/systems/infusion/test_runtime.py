from __future__ import annotations

import json

import pytest

from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.events import EventEngine, EventType
from genshin_sim.core.systems.infusion import (
    ApplyInfusionRequest,
    EffectiveElementReason,
    InfusionApplicationOutcome,
    InfusionDefinition,
    InfusionDefinitionRegistry,
    InfusionLifecycleState,
    InfusionMode,
    InfusionPlanConflictError,
    InfusionReentrancyError,
    InfusionRemovalReason,
    InfusionResolver,
    InfusionRuntime,
    InfusionStore,
    InfusionSystemError,
    RefreshPolicy,
    RemoveInfusionRequest,
)
from tests.helpers.infusion import (
    CHARACTER,
    SOURCE,
    SOURCE_2,
    make_definition,
    make_request,
)


def test_runtime_apply_create_and_refresh_publish_stable_events():
    definition = make_definition(duration_frames=10)
    runtime = _runtime(definition)
    created = runtime.apply(make_request("req:1", definition))
    assert created.outcome is InfusionApplicationOutcome.CREATED
    assert created.next_refresh_frame_after is None
    assert [event.event_type for event in runtime.event_engine.frame_events] == [
        EventType.INFUSION_APPLIED
    ]
    payload = json.loads(json.dumps(runtime.event_engine.frame_events[-1].payload.to_dict()))
    assert payload["result"]["outcome"] == "created"
    assert payload["result"]["element"] == "pyro"

    refreshed = runtime.apply(make_request("req:2", definition, frame=2))
    assert refreshed.outcome is InfusionApplicationOutcome.REFRESHED
    assert refreshed.instance_ref == created.instance_ref
    assert refreshed.expires_at_after == 12
    assert runtime.infusion_store.records == (runtime.infusion_store.require(created.instance_ref),)
    assert [event.event_type for event in runtime.event_engine.frame_events] == [
        EventType.INFUSION_APPLIED,
        EventType.INFUSION_APPLIED,
    ]


def test_runtime_conversion_replace_publishes_removed_then_applied():
    first = make_definition(
        definition_key="infusion.test.conversion.1",
        mode=InfusionMode.CONVERSION,
        element=Element.HYDRO,
    )
    second = make_definition(
        definition_key="infusion.test.conversion.2",
        mode=InfusionMode.CONVERSION,
        element=Element.CRYO,
    )
    runtime = _runtime(first, second)
    created = runtime.apply(make_request("req:1", first))
    replaced = runtime.apply(make_request("req:2", second, frame=1))
    assert replaced.outcome is InfusionApplicationOutcome.REPLACED
    assert replaced.replaced_instance_refs == (created.instance_ref,)
    assert runtime.infusion_store.require(created.instance_ref).removal_reason is (
        InfusionRemovalReason.REPLACED
    )
    assert [event.event_type for event in runtime.event_engine.frame_events] == [
        EventType.INFUSION_APPLIED,
        EventType.INFUSION_REMOVED,
        EventType.INFUSION_APPLIED,
    ]


def test_runtime_batch_atomicity_and_deduplication():
    definition = make_definition()
    runtime = _runtime(definition)
    valid = make_request("batch:1", definition, order=0)
    invalid_definition_key = ApplyInfusionRequest(
        request_id="batch:3",
        frame=0,
        order=2,
        definition_key="missing",
        character_ref=CHARACTER,
        source_context=SOURCE,
    )

    with pytest.raises(InfusionSystemError, match="definition_key"):
        runtime.apply_many((valid, invalid_definition_key))
    assert runtime.infusion_store.records == ()

    runtime.apply(valid)
    with pytest.raises(InfusionPlanConflictError, match="已提交"):
        runtime.apply(valid)
    with pytest.raises(InfusionSystemError, match="order"):
        runtime.apply_many(
            (
                make_request("batch:4", definition, order=0),
                make_request("batch:5", definition, order=0),
            )
        )
    with pytest.raises(InfusionSystemError, match="frame"):
        runtime.apply_many(
            (
                make_request("batch:6", definition, frame=0),
                make_request("batch:7", definition, frame=1),
            )
        )
    assert len(runtime.infusion_store.records) == 1


def test_runtime_remove_and_expiry_boundaries_with_events():
    definition = make_definition(duration_frames=3)
    runtime = _runtime(definition)
    created = runtime.apply(make_request("req:1", definition, frame=100))
    assert runtime.infusion_store.require(created.instance_ref).is_active_at(102)

    removed = runtime.remove(
        RemoveInfusionRequest(
            request_id="remove:1",
            frame=101,
            instance_ref=created.instance_ref,
            reason=InfusionRemovalReason.EXPLICIT,
        )
    )
    assert removed.reason is InfusionRemovalReason.EXPLICIT
    assert runtime.event_engine.frame_events[-1].event_type is EventType.INFUSION_REMOVED
    assert runtime.infusion_store.require(created.instance_ref).is_active_at(101) is False


def test_runtime_frame_expiry_marks_expired_lifecycle_and_snapshot():
    definition = make_definition(duration_frames=3)
    runtime = _runtime(definition)
    created = runtime.apply(make_request("req:1", definition, frame=100))
    version_before = runtime.infusion_store.version
    assert len(runtime.snapshot(102).instances) == 1

    runtime.update_frame(None, 103)
    record = runtime.infusion_store.require(created.instance_ref)
    assert record.lifecycle_state is InfusionLifecycleState.EXPIRED
    assert record.removal_reason is InfusionRemovalReason.EXPIRED
    assert runtime.infusion_store.version == version_before + 1
    assert runtime.event_engine.frame_events[-1].event_type is EventType.INFUSION_REMOVED
    assert json.loads(json.dumps(runtime.snapshot(103).to_dict()))["instances"] == []


def test_runtime_resolve_effective_element_and_periodic_apply():
    infusion = make_definition(element=Element.PYRO)
    conversion = make_definition(
        definition_key="infusion.test.conversion",
        mode=InfusionMode.CONVERSION,
        element=Element.CRYO,
    )
    periodic = make_definition(
        definition_key="infusion.test.periodic",
        refresh_policy=RefreshPolicy.PERIODIC,
        period_frames=5,
        element=Element.ELECTRO,
    )
    runtime = _runtime(infusion, conversion, periodic)

    base = runtime.resolve_effective_element(0, CHARACTER, Element.PHYSICAL)
    assert base.element is Element.PHYSICAL
    assert base.reason is EffectiveElementReason.NO_ACTIVE_SOURCE

    runtime.apply(make_request("req:1", infusion))
    single = runtime.resolve_effective_element(0, CHARACTER, Element.PHYSICAL)
    assert single.element is Element.PYRO
    assert single.reason is EffectiveElementReason.SINGLE_SOURCE

    runtime.apply(make_request("req:2", conversion, frame=1))
    converted = runtime.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert converted.element is Element.CRYO
    assert converted.mode is InfusionMode.CONVERSION

    applied = runtime.apply(make_request("req:3", periodic, frame=2))
    assert applied.next_refresh_frame_after == 7
    record = runtime.infusion_store.require(applied.instance_ref)
    assert record.refresh_policy is RefreshPolicy.PERIODIC
    assert record.next_refresh_frame == 7
    assert record.remaining_gauge == AuraAmount(0)
    still_converted = runtime.resolve_effective_element(2, CHARACTER, Element.PHYSICAL)
    assert still_converted.element is Element.CRYO


def test_runtime_same_element_multi_source_latest_controls():
    first = make_definition(definition_key="infusion.test.first")
    second = make_definition(definition_key="infusion.test.second")
    runtime = _runtime(first, second)
    runtime.apply(make_request("req:1", first))
    runtime.apply(make_request("req:2", second, frame=1, source_context=SOURCE_2))
    resolution = runtime.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.PYRO
    assert resolution.reason is EffectiveElementReason.SINGLE_SOURCE
    assert resolution.source_refs == (SOURCE, SOURCE_2)
    assert len(runtime.infusion_store.active(1, character_ref=CHARACTER)) == 2


def test_runtime_rejects_synchronous_reentry_during_event_publish():
    definition = make_definition()
    runtime = _runtime(definition)
    seen: list[str] = []

    def reenter(_event):
        with pytest.raises(InfusionReentrancyError):
            runtime.apply(make_request("reenter:2", definition, frame=1))
        seen.append("blocked")

    runtime.event_engine.subscribe(EventType.INFUSION_APPLIED, reenter)
    runtime.apply(make_request("reenter:1", definition))
    assert seen == ["blocked"]


def _runtime(*definitions: InfusionDefinition) -> InfusionRuntime:
    return InfusionRuntime(
        definition_registry=InfusionDefinitionRegistry(tuple(definitions)),
        resolver=InfusionResolver(),
        infusion_store=InfusionStore(),
        event_engine=EventEngine(),
    )
