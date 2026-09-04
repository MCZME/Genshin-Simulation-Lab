from decimal import Decimal

import pytest

from genshin_sim.core.events import CooldownChangedPayload, EventEngine, EventType
from genshin_sim.core.systems.cooldown import (
    AbilityKind,
    CooldownDefinition,
    CooldownDurationMode,
    CooldownDurationOperation,
    CooldownDurationResolver,
    CooldownDurationStage,
    CooldownDurationTerm,
    CooldownKey,
    CooldownMutationBatchRequest,
    CooldownNotNormalizedError,
    CooldownRuntime,
    CooldownStore,
    CooldownSubjectRef,
    DuplicateCooldownRequestError,
    ReduceRemainingCooldownRequest,
    ResetActiveCooldownRequest,
    StartCooldownRequest,
)


def _key(ability_key: str = "elemental_skill") -> CooldownKey:
    return CooldownKey(CooldownSubjectRef.character("character:slot_1"), ability_key)


def _runtime(
    *,
    duration: int = 600,
    charges: int = 1,
    mode: CooldownDurationMode = CooldownDurationMode.FIXED,
    event_engine: EventEngine | None = None,
) -> CooldownRuntime:
    definition = CooldownDefinition(
        _key(), AbilityKind.ELEMENTAL_SKILL, duration, charges, mode, "test:definition"
    )
    return CooldownRuntime(CooldownStore((definition,)), event_engine=event_engine)


def _start(
    runtime: CooldownRuntime,
    request_id: str,
    frame: int,
    **kwargs,
):
    return runtime.start(StartCooldownRequest(request_id, _key(), frame, "test:action", **kwargs))


def test_fixed_cooldown_requires_explicit_normalization_and_recovers_at_ready_frame():
    runtime = _runtime(duration=1920)

    with pytest.raises(CooldownNotNormalizedError):
        _start(runtime, "start:1", 100)

    runtime.normalize(100)
    result = _start(runtime, "start:1", 100)
    assert result is not None and result.applied
    assert runtime.query_condition(runtime_query(_key(), 100)).satisfied is False

    runtime.normalize(2019)
    assert runtime.query_condition(runtime_query(_key(), 2019)).satisfied is False
    normalized = runtime.normalize(2020)
    assert runtime.query_condition(runtime_query(_key(), 2020)).satisfied is True
    assert [fact.frame for fact in normalized.facts] == [2020, 2020]


def test_cooldown_start_and_recovery_publish_state_change_events():
    engine = EventEngine()
    runtime = _runtime(duration=600, event_engine=engine)
    runtime.normalize(100)

    result = _start(runtime, "start:1", 100)
    assert result is not None and result.applied

    start_events = [
        event for event in engine.frame_events if event.event_type is EventType.COOLDOWN_CHANGED
    ]
    assert len(start_events) == 1
    payload = start_events[0].payload
    assert isinstance(payload, CooldownChangedPayload)
    assert payload.fact_kind == "started"
    assert payload.before_available_charges == 1
    assert payload.after_available_charges == 0
    assert payload.active_ready_frame == 700
    assert payload.before_record is not None
    assert payload.after_record is not None
    assert payload.before_record["available_charges"] == 1
    assert payload.after_record["available_charges"] == 0
    assert payload.after_record["active_ready_frame"] == 700
    assert payload.after_record["active_started_frame"] == 100
    assert payload.after_record["interval_frames"] == 600
    assert payload.after_record["revision"] == 1

    engine.clear_frame_events()
    runtime.normalize(700)

    recovery_events = [
        event for event in engine.frame_events if event.event_type is EventType.COOLDOWN_CHANGED
    ]
    assert any(
        isinstance(event.payload, CooldownChangedPayload)
        and event.payload.fact_kind == "charge_recovered"
        for event in recovery_events
    )


def test_multi_charge_uses_serial_recovery_and_snapshots_first_duration_resolution():
    runtime = _runtime(charges=2)
    runtime.normalize(100)
    term = CooldownDurationTerm(
        "c2",
        "test:c2",
        CooldownDurationStage.OWNER_ADJUSTMENT,
        CooldownDurationOperation.MULTIPLY_CURRENT,
        Decimal("0.85"),
    )
    first = _start(runtime, "start:first", 100, duration_terms=(term,))
    assert first is not None and first.after.active_recovery is not None
    assert first.after.active_recovery.ready_frame == 610

    runtime.normalize(120)
    second = _start(runtime, "start:second", 120)
    assert second is not None and second.reused_chain_resolution
    assert second.after.active_recovery is not None
    assert second.after.active_recovery.ready_frame == 610
    assert second.after.queued_recoveries == 1

    runtime.normalize(610)
    record = runtime.store.get_record(_key())
    assert record.available_charges == 1
    assert record.active_recovery is not None and record.active_recovery.ready_frame == 1120
    runtime.normalize(1120)
    assert runtime.store.get_record(_key()).available_charges == 2


def test_reduce_and_reset_only_finish_current_recovery_without_carrying_overflow():
    runtime = _runtime(duration=100, charges=2)
    runtime.normalize(0)
    _start(runtime, "start:1", 0)
    _start(runtime, "start:2", 0)
    runtime.normalize(70)

    result = runtime.reduce_remaining(
        ReduceRemainingCooldownRequest("reduce", _key(), 70, 60, "test:reduction")
    )
    assert result.applied
    record = runtime.store.get_record(_key())
    assert record.available_charges == 1
    assert record.active_recovery is not None and record.active_recovery.ready_frame == 170

    runtime.normalize(120)
    reset = runtime.reset_active(ResetActiveCooldownRequest("reset", _key(), 120, "test:reset"))
    assert reset.applied
    assert runtime.store.get_record(_key()).available_charges == 2


def test_request_provided_duration_and_batch_are_atomic_and_idempotent():
    runtime = _runtime(duration=1, mode=CooldownDurationMode.REQUEST_PROVIDED)
    runtime.normalize(10)
    result = _start(runtime, "dynamic", 10, requested_base_duration_frames=42)
    assert result is not None and result.resolution is not None
    assert result.resolution.resolved_duration_frames == 42

    with pytest.raises(DuplicateCooldownRequestError):
        _start(runtime, "dynamic", 10, requested_base_duration_frames=42)

    second_key = CooldownKey(CooldownSubjectRef.character("character:slot_2"), "elemental_skill")
    second = CooldownDefinition(
        second_key,
        AbilityKind.ELEMENTAL_SKILL,
        10,
        1,
        CooldownDurationMode.FIXED,
        "test:second",
    )
    first_definition = _runtime().store.get_definition(_key())
    batch_runtime = CooldownRuntime(CooldownStore((first_definition, second)))
    batch_runtime.normalize(0)
    batch = CooldownMutationBatchRequest(
        "batch:1",
        0,
        (
            StartCooldownRequest("batch:first", _key(), 0, "test"),
            StartCooldownRequest("batch:second", second_key, 0, "test"),
        ),
    )
    outcome = batch_runtime.mutate_batch(batch)
    assert all(item.applied for item in outcome.item_results)
    with pytest.raises(DuplicateCooldownRequestError):
        batch_runtime.start(StartCooldownRequest("batch:first", _key(), 0, "test"))


def test_normalize_operation_id_never_collides_with_external_request_id():
    runtime = _runtime(duration=1)
    runtime.normalize(0)
    _start(runtime, "normalize:1", 0)

    normalized = runtime.normalize(1)

    assert runtime.query_condition(runtime_query(_key(), 1)).satisfied
    assert normalized.changed_records[0].available_charges == 1


def test_duration_audit_terms_use_the_same_stage_order_as_resolution():
    definition = _runtime().store.get_definition(_key())
    duration = CooldownDurationResolver().resolve(
        definition,
        None,
        (
            CooldownDurationTerm(
                "increase",
                "test:increase",
                CooldownDurationStage.DURATION_INCREASE,
                CooldownDurationOperation.MULTIPLY_CURRENT,
                Decimal("1.2"),
            ),
            CooldownDurationTerm(
                "owner",
                "test:owner",
                CooldownDurationStage.OWNER_ADJUSTMENT,
                CooldownDurationOperation.MULTIPLY_CURRENT,
                Decimal("0.8"),
            ),
        ),
    )

    assert [term.stage for term in duration.terms] == [
        CooldownDurationStage.OWNER_ADJUSTMENT,
        CooldownDurationStage.DURATION_INCREASE,
    ]


def runtime_query(key: CooldownKey, frame: int):
    from genshin_sim.core.systems.cooldown import CooldownQuery

    return CooldownQuery(key, frame)
