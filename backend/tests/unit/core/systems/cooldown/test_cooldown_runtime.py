import json
from decimal import Decimal
from typing import cast

import pytest

from genshin_sim.core.events import CooldownChangedPayload, EventEngine, EventType
from genshin_sim.core.systems.cooldown import (
    AbilityKind,
    ActiveRecovery,
    CooldownDefinition,
    CooldownDurationMode,
    CooldownDurationOperation,
    CooldownDurationResolution,
    CooldownDurationResolver,
    CooldownDurationStage,
    CooldownDurationTerm,
    CooldownInvariantError,
    CooldownKey,
    CooldownMutationBatchRequest,
    CooldownNotNormalizedError,
    CooldownQuery,
    CooldownRecord,
    CooldownRecoveryMode,
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


def _definition(
    *,
    duration: int = 600,
    charges: int = 1,
    mode: CooldownDurationMode = CooldownDurationMode.FIXED,
    recovery_mode: CooldownRecoveryMode = CooldownRecoveryMode.SERIAL,
) -> CooldownDefinition:
    return CooldownDefinition(
        _key(),
        AbilityKind.ELEMENTAL_SKILL,
        duration,
        charges,
        mode,
        "test:definition",
        recovery_mode=recovery_mode,
    )


def _runtime(
    *,
    duration: int = 600,
    charges: int = 1,
    mode: CooldownDurationMode = CooldownDurationMode.FIXED,
    recovery_mode: CooldownRecoveryMode = CooldownRecoveryMode.SERIAL,
    event_engine: EventEngine | None = None,
) -> CooldownRuntime:
    definition = _definition(
        duration=duration, charges=charges, mode=mode, recovery_mode=recovery_mode
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

    # 串行只维护一条在途链：新充能排队，不新开链。
    record = runtime.store.get_record(_key())
    assert record.recovery_mode is CooldownRecoveryMode.SERIAL
    assert (record.pending_recoveries, record.queued_recoveries) == (1, 1)
    view = runtime.query_condition(runtime_query(_key(), 120)).view
    assert view.recovery_mode is CooldownRecoveryMode.SERIAL
    assert (view.pending_recoveries, view.queued_recoveries) == (1, 1)

    normalized_chain = runtime.normalize(610)
    record = runtime.store.get_record(_key())
    assert record.available_charges == 1
    assert record.active_recovery is not None and record.active_recovery.ready_frame == 1120
    # 到期充能回收，续转的充能继承首链 id 与新的就绪帧。
    assert [fact.fact_kind.value for fact in normalized_chain.facts] == ["charge_recovered"]
    assert normalized_chain.facts[0].chain_id == "cooldown-chain:start:first"
    assert normalized_chain.facts[0].active_ready_frame == 1120

    drained = runtime.normalize(1120)
    assert [fact.fact_kind.value for fact in drained.facts] == [
        "charge_recovered",
        "chain_completed",
    ]
    assert drained.facts[0].chain_id is None
    assert drained.facts[1].chain_id == "cooldown-chain:start:first"
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


def test_independent_recovery_runs_each_charge_on_its_own_timer_and_duration():
    runtime = _runtime(duration=900, charges=2, recovery_mode=CooldownRecoveryMode.INDEPENDENT)
    halve = CooldownDurationTerm(
        "halve",
        "test:halve",
        CooldownDurationStage.OWNER_ADJUSTMENT,
        CooldownDurationOperation.MULTIPLY_CURRENT,
        Decimal("0.5"),
    )
    runtime.normalize(100)
    first = _start(runtime, "start:first", 100, duration_terms=(halve,))
    runtime.normalize(200)
    second = _start(runtime, "start:second", 200)

    # 独立模式不共享链：每次施放各自解析时长，各自计时。
    assert first is not None and first.resolution is not None
    assert first.resolution.resolved_duration_frames == 450
    assert second is not None and second.applied and not second.reused_chain_resolution
    assert second.resolution is not None and second.resolution.resolved_duration_frames == 900
    record = runtime.store.get_record(_key())
    assert [item.ready_frame for item in record.recoveries] == [550, 1100]
    assert [item.interval_frames for item in record.recoveries] == [450, 900]
    assert record.queued_recoveries == 0
    assert record.available_charges == 0

    view = runtime.query_condition(runtime_query(_key(), 200)).view
    assert view.recovery_mode is CooldownRecoveryMode.INDEPENDENT
    assert (view.pending_recoveries, view.queued_recoveries) == (2, 0)
    assert view.active_ready_frame == 550
    assert view.remaining_frames == 350

    at_550 = runtime.normalize(550)
    assert [fact.fact_kind.value for fact in at_550.facts] == [
        "charge_recovered",
        "chain_completed",
    ]
    assert {fact.chain_id for fact in at_550.facts} == {"cooldown-chain:start:first"}
    after_first = runtime.store.get_record(_key())
    assert after_first.available_charges == 1
    assert [item.ready_frame for item in after_first.recoveries] == [1100]

    at_1100 = runtime.normalize(1100)
    assert [fact.fact_kind.value for fact in at_1100.facts] == [
        "charge_recovered",
        "chain_completed",
    ]
    assert {fact.chain_id for fact in at_1100.facts} == {"cooldown-chain:start:second"}
    final = runtime.store.get_record(_key())
    assert final.available_charges == 2
    assert final.recoveries == ()


def test_independent_reduce_and_reset_target_the_earliest_pending_recovery():
    runtime = _runtime(duration=900, charges=2, recovery_mode=CooldownRecoveryMode.INDEPENDENT)
    runtime.normalize(0)
    _start(runtime, "start:first", 0)
    runtime.normalize(100)
    _start(runtime, "start:second", 100)

    runtime.normalize(200)
    reduced = runtime.reduce_remaining(
        ReduceRemainingCooldownRequest("reduce", _key(), 200, 300, "test:reduction")
    )
    assert reduced.applied
    record = runtime.store.get_record(_key())
    assert record.available_charges == 0
    assert [item.ready_frame for item in record.recoveries] == [600, 1000]
    assert [item.interval_frames for item in record.recoveries] == [600, 900]

    runtime.normalize(600)
    assert runtime.store.get_record(_key()).available_charges == 1
    assert [item.ready_frame for item in runtime.store.get_record(_key()).recoveries] == [1000]

    runtime.normalize(700)
    reset = runtime.reset_active(ResetActiveCooldownRequest("reset", _key(), 700, "test:reset"))
    assert reset.applied
    final = runtime.store.get_record(_key())
    assert final.available_charges == 2
    assert final.recoveries == ()

    # 无在途恢复项时 reduce 是空操作：不改状态、不产出事实。
    ignored = runtime.reduce_remaining(
        ReduceRemainingCooldownRequest("reduce:noop", _key(), 700, 60, "test:reduction")
    )
    assert not ignored.applied
    assert [fact.fact_kind.value for fact in ignored.facts] == []
    assert runtime.store.get_record(_key()).available_charges == 2


def test_record_invariants_separate_serial_and_independent_recovery_states():
    with pytest.raises(CooldownInvariantError, match="至多一个在途恢复项"):
        CooldownRecord(
            _key(),
            AbilityKind.ELEMENTAL_SKILL,
            2,
            0,
            CooldownRecoveryMode.SERIAL,
            (_recovery(900, "cooldown-chain:a"), _recovery(1900, "cooldown-chain:b")),
        )
    with pytest.raises(CooldownInvariantError, match="不存在排队次数"):
        CooldownRecord(
            _key(),
            AbilityKind.ELEMENTAL_SKILL,
            2,
            1,
            CooldownRecoveryMode.INDEPENDENT,
            (_recovery(900, "cooldown-chain:a"),),
            1,
        )
    with pytest.raises(CooldownInvariantError, match="不守恒"):
        CooldownRecord(
            _key(),
            AbilityKind.ELEMENTAL_SKILL,
            2,
            2,
            CooldownRecoveryMode.INDEPENDENT,
            (_recovery(900, "cooldown-chain:a"),),
        )

    record = CooldownRecord(
        _key(),
        AbilityKind.ELEMENTAL_SKILL,
        2,
        0,
        CooldownRecoveryMode.INDEPENDENT,
        (_recovery(1100, "cooldown-chain:b"), _recovery(900, "cooldown-chain:a")),
    )
    assert [item.chain_id for item in record.recoveries] == [
        "cooldown-chain:a",
        "cooldown-chain:b",
    ]
    assert record.active_recovery is not None and record.active_recovery.ready_frame == 900
    assert record.pending_recoveries == 2


def test_independent_snapshot_and_events_carry_every_pending_recovery():
    engine = EventEngine()
    runtime = _runtime(
        duration=900,
        charges=2,
        recovery_mode=CooldownRecoveryMode.INDEPENDENT,
        event_engine=engine,
    )
    runtime.normalize(100)
    _start(runtime, "start:first", 100)
    runtime.normalize(200)
    _start(runtime, "start:second", 200)

    snapshot = runtime.snapshot(200).to_dict()
    assert snapshot["schema_version"] == 2
    records = cast(list[dict[str, object]], snapshot["records"])
    assert records[0]["recovery_mode"] == "independent"
    recoveries = cast(list[dict[str, object]], records[0]["recoveries"])
    assert [item["ready_frame"] for item in recoveries] == [1000, 1100]
    assert [item["interval_frames"] for item in recoveries] == [900, 900]
    assert records[0]["active_ready_frame"] == 1000
    assert records[0]["chain_id"] == "cooldown-chain:start:first"
    assert records[0]["queued_recoveries"] == 0
    round_tripped = json.loads(json.dumps(snapshot))
    assert round_tripped["records"][0]["recoveries"][1]["ready_frame"] == 1100

    events = [
        event for event in engine.frame_events if event.event_type is EventType.COOLDOWN_CHANGED
    ]
    assert len(events) == 2
    payload = events[-1].payload
    assert isinstance(payload, CooldownChangedPayload)
    assert payload.after_record is not None
    emitted = cast(list[dict[str, object]], payload.after_record["recoveries"])
    assert [item["ready_frame"] for item in emitted] == [1000, 1100]
    assert payload.after_record["recovery_mode"] == "independent"


def _recovery(ready_frame: int, chain_id: str) -> ActiveRecovery:
    return ActiveRecovery(
        started_frame=0,
        ready_frame=ready_frame,
        interval_frames=ready_frame,
        chain_id=chain_id,
        start_source_ref="test:action",
        duration_audit=CooldownDurationResolution(
            base_duration_frames=ready_frame,
            resolved_duration_frames=ready_frame,
            terms=(),
            stage_totals=(),
            rounded_from=None,
            source_refs=("test:definition",),
        ),
    )


def runtime_query(key: CooldownKey, frame: int) -> CooldownQuery:
    return CooldownQuery(key, frame)
