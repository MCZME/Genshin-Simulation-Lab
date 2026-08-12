from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import Protocol

from genshin_sim.core.events import EventEngine, EventType, GameEvent
from genshin_sim.core.systems.cooldown.enums import (
    CooldownConditionReason,
    CooldownFactKind,
    CooldownMutationReason,
)
from genshin_sim.core.systems.cooldown.errors import (
    CooldownFrameRegressionError,
    CooldownNotNormalizedError,
    CooldownReentrancyError,
    CooldownValidationError,
)
from genshin_sim.core.systems.cooldown.models import (
    ActiveRecovery,
    CooldownConditionResult,
    CooldownFact,
    CooldownKey,
    CooldownMutationBatchPlan,
    CooldownMutationBatchRequest,
    CooldownMutationBatchResult,
    CooldownMutationPlan,
    CooldownMutationRequest,
    CooldownMutationResult,
    CooldownQuery,
    CooldownRecord,
    CooldownView,
    NormalizeCooldownsResult,
    PrepareStartCooldownResult,
    ReduceRemainingCooldownRequest,
    ResetActiveCooldownRequest,
    StartCooldownRequest,
)
from genshin_sim.core.systems.cooldown.resolver import CooldownDurationResolver
from genshin_sim.core.systems.cooldown.snapshots import (
    CooldownRecordSnapshot,
    CooldownSnapshot,
)
from genshin_sim.core.systems.cooldown.store import CooldownStore


class CooldownConditionReadPort(Protocol):
    def query_condition(self, query: CooldownQuery) -> CooldownConditionResult: ...


class CooldownRuntime:
    """冷却领域唯一写入口；不会发布跨系统事件或调用外部回调。"""

    def __init__(
        self,
        store: CooldownStore,
        resolver: CooldownDurationResolver | None = None,
        event_engine: EventEngine | None = None,
    ) -> None:
        self.store = store
        self.resolver = resolver or CooldownDurationResolver()
        self.event_engine = event_engine
        self.normalized_through_frame = 0
        self._mutation_active = False
        self._batch_preparing = False

    def update_frame(self, context: object, frame: int) -> NormalizeCooldownsResult:
        del context
        return self.normalize(frame)

    def is_idle(self) -> bool:
        return all(record.active_recovery is None for record in self.store.records)

    def normalize(self, frame: int) -> NormalizeCooldownsResult:
        self._assert_not_regressed(frame)
        if frame == self.normalized_through_frame:
            return NormalizeCooldownsResult(frame, (), ())
        with self._mutation_scope():
            expected = {record.key: record for record in self.store.records}
            changed: dict[CooldownKey, CooldownRecord] = {}
            facts: list[CooldownFact] = []
            for before in self.store.records:
                after, record_facts = self._normalize_record(before, frame, f"normalize:{frame}")
                if after != before:
                    changed[before.key] = after
                    facts.extend(record_facts)
            if changed:
                self.store.assert_can_commit(None, self.store.version, expected)
                self.store.commit_prevalidated(None, changed)
            self.normalized_through_frame = frame
            facts.sort(key=lambda item: item.sort_key)
            result = NormalizeCooldownsResult(frame, tuple(changed.values()), tuple(facts))
        self._publish_facts(result.facts)
        return result

    def query_condition(self, query: CooldownQuery) -> CooldownConditionResult:
        self._require_normalized(query.frame)
        record = self.store.get_record(query.key)
        active = record.active_recovery
        view = CooldownView(
            key=record.key,
            ability_kind=record.ability_kind,
            max_charges=record.max_charges,
            available_charges=record.available_charges,
            active_ready_frame=None if active is None else active.ready_frame,
            remaining_frames=0 if active is None else max(0, active.ready_frame - query.frame),
            queued_recoveries=record.queued_recoveries,
            chain_id=None if active is None else active.chain_id,
            revision=record.revision,
        )
        satisfied = record.available_charges > 0
        return CooldownConditionResult(
            query=query,
            satisfied=satisfied,
            reason=(
                CooldownConditionReason.CHARGE_AVAILABLE
                if satisfied
                else CooldownConditionReason.NO_AVAILABLE_CHARGE
            ),
            view=view,
        )

    def prepare_start(self, request: StartCooldownRequest) -> PrepareStartCooldownResult:
        with self._mutation_scope():
            self._require_normalized(request.frame)
            self.store.assert_request_available(request.request_id)
            definition = self.store.get_definition(request.key)
            before = self.store.get_record(request.key)
            condition = self.query_condition(CooldownQuery(request.key, request.frame))
            if not condition.satisfied:
                return PrepareStartCooldownResult(condition, None)
            if before.active_recovery is None:
                resolution = self.resolver.resolve(
                    definition, request.requested_base_duration_frames, request.duration_terms
                )
                chain_id = f"cooldown-chain:{request.request_id}"
                active = ActiveRecovery(
                    started_frame=request.frame,
                    ready_frame=request.frame + resolution.resolved_duration_frames,
                    interval_frames=resolution.resolved_duration_frames,
                    chain_id=chain_id,
                    start_source_ref=request.source_ref,
                    duration_audit=resolution,
                )
                after = replace(
                    before,
                    available_charges=before.available_charges - 1,
                    active_recovery=active,
                    revision=before.revision + 1,
                    last_changed_frame=request.frame,
                )
                facts = [self._fact(CooldownFactKind.STARTED, request, before, after, resolution)]
                if active.interval_frames == 0:
                    after, recovery_facts = self._complete_active(
                        after, request.frame, request, False
                    )
                    facts.extend(recovery_facts)
                plan = CooldownMutationPlan(
                    request.request_id,
                    request.key,
                    self.store.version,
                    before.revision,
                    before,
                    after,
                    tuple(facts),
                    resolution,
                    False,
                )
            else:
                active = before.active_recovery
                after = replace(
                    before,
                    available_charges=before.available_charges - 1,
                    queued_recoveries=before.queued_recoveries + 1,
                    revision=before.revision + 1,
                    last_changed_frame=request.frame,
                )
                plan = CooldownMutationPlan(
                    request.request_id,
                    request.key,
                    self.store.version,
                    before.revision,
                    before,
                    after,
                    (
                        self._fact(
                            CooldownFactKind.STARTED, request, before, after, active.duration_audit
                        ),
                    ),
                    active.duration_audit,
                    True,
                )
            return PrepareStartCooldownResult(condition, plan)

    def start(self, request: StartCooldownRequest) -> CooldownMutationResult | None:
        prepared = self.prepare_start(request)
        return None if prepared.plan is None else self.commit(prepared.plan)

    def prepare_reduce(self, request: ReduceRemainingCooldownRequest) -> CooldownMutationPlan:
        return self._prepare_modify(request, CooldownFactKind.REDUCED)

    def reduce_remaining(self, request: ReduceRemainingCooldownRequest) -> CooldownMutationResult:
        return self.commit(self.prepare_reduce(request))

    def prepare_reset(self, request: ResetActiveCooldownRequest) -> CooldownMutationPlan:
        return self._prepare_modify(request, CooldownFactKind.RESET)

    def reset_active(self, request: ResetActiveCooldownRequest) -> CooldownMutationResult:
        return self.commit(self.prepare_reset(request))

    def commit(self, plan: CooldownMutationPlan) -> CooldownMutationResult:
        with self._mutation_scope():
            self.store.assert_can_commit(
                plan.request_id,
                plan.expected_store_revision,
                {plan.key: plan.before},
            )
            records = {} if plan.after == plan.before else {plan.key: plan.after}
            self.store.commit_prevalidated(plan.request_id, records)
            result = self._result(plan)
        self._publish_facts(plan.facts)
        return result

    def prepare_batch(self, request: CooldownMutationBatchRequest) -> CooldownMutationBatchPlan:
        with self._mutation_scope():
            self._batch_preparing = True
            try:
                self._require_normalized(request.frame)
                ordered = tuple(
                    sorted(request.requests, key=lambda item: (item.key.sort_key, item.request_id))
                )
                keys = [item.key for item in ordered]
                request_ids = [item.request_id for item in ordered]
                if len(keys) != len(set(keys)):
                    raise CooldownValidationError("同一 batch 不能修改同一个 cooldown key 多次")
                if len(request_ids) != len(set(request_ids)):
                    raise CooldownValidationError("同一 batch 不能使用重复 request_id")
                plans: list[CooldownMutationPlan] = []
                for item in ordered:
                    plan = self._prepare_item(item)
                    if plan.expected_store_revision != self.store.version:
                        raise CooldownValidationError("batch plan 使用了错误的 Store revision")
                    plans.append(plan)
                facts = tuple(
                    sorted(
                        (fact for plan in plans for fact in plan.facts),
                        key=lambda item: item.sort_key,
                    )
                )
                return CooldownMutationBatchPlan(
                    request.batch_id, request.frame, self.store.version, tuple(plans), facts
                )
            finally:
                self._batch_preparing = False

    def commit_batch(self, plan: CooldownMutationBatchPlan) -> CooldownMutationBatchResult:
        with self._mutation_scope():
            expected = {item.key: item.before for item in plan.item_plans}
            request_ids = tuple(item.request_id for item in plan.item_plans)
            self.store.assert_can_commit(
                plan.batch_id,
                plan.expected_store_revision,
                expected,
                request_ids,
            )
            records = {
                item.key: item.after for item in plan.item_plans if item.after != item.before
            }
            self.store.commit_prevalidated(plan.batch_id, records, request_ids)
            results = tuple(self._result(item) for item in plan.item_plans)
            result = CooldownMutationBatchResult(plan.batch_id, plan.frame, results, plan.facts)
        self._publish_facts(plan.facts)
        return result

    def mutate_batch(self, request: CooldownMutationBatchRequest) -> CooldownMutationBatchResult:
        return self.commit_batch(self.prepare_batch(request))

    def snapshot(self, frame: int) -> CooldownSnapshot:
        self._require_normalized(frame)
        return CooldownSnapshot(
            schema_version=1,
            frame=frame,
            normalized_through_frame=self.normalized_through_frame,
            records=tuple(CooldownRecordSnapshot.from_record(item) for item in self.store.records),
        )

    def _publish_facts(self, facts: tuple[CooldownFact, ...]) -> None:
        if self.event_engine is None or not facts:
            return
        from genshin_sim.core.events.payloads import CooldownChangedPayload

        for fact in facts:
            before_record = (
                None
                if fact.before_record is None
                else CooldownRecordSnapshot.from_record(fact.before_record).to_dict()
            )
            after_record = (
                None
                if fact.after_record is None
                else CooldownRecordSnapshot.from_record(fact.after_record).to_dict()
            )
            self.event_engine.publish(
                GameEvent(
                    EventType.COOLDOWN_CHANGED,
                    frame=fact.frame,
                    source=self,
                    payload=CooldownChangedPayload(
                        fact_id=fact.fact_id,
                        fact_kind=fact.fact_kind.value,
                        frame=fact.frame,
                        subject_ref={
                            "subject_type": fact.key.subject.subject_type.value,
                            "subject_id": fact.key.subject.subject_id,
                        },
                        ability_key=fact.key.ability_key,
                        operation_id=fact.operation_id,
                        chain_id=fact.chain_id,
                        before_available_charges=fact.before_available_charges,
                        after_available_charges=fact.after_available_charges,
                        active_ready_frame=fact.active_ready_frame,
                        queued_recoveries=fact.queued_recoveries,
                        source_ref=fact.source_ref,
                        before_record=before_record,
                        after_record=after_record,
                    ),
                )
            )

    def _prepare_item(self, request: CooldownMutationRequest) -> CooldownMutationPlan:
        if isinstance(request, StartCooldownRequest):
            prepared = self.prepare_start(request)
            if prepared.plan is None:
                before = self.store.get_record(request.key)
                return CooldownMutationPlan(
                    request.request_id,
                    request.key,
                    self.store.version,
                    before.revision,
                    before,
                    before,
                    (),
                    ignored_reason=CooldownMutationReason.NO_EFFECT,
                )
            return prepared.plan
        if isinstance(request, ReduceRemainingCooldownRequest):
            return self.prepare_reduce(request)
        return self.prepare_reset(request)

    def _prepare_modify(
        self,
        request: ReduceRemainingCooldownRequest | ResetActiveCooldownRequest,
        fact_kind: CooldownFactKind,
    ) -> CooldownMutationPlan:
        with self._mutation_scope():
            self._require_normalized(request.frame)
            self.store.assert_request_available(request.request_id)
            before = self.store.get_record(request.key)
            active = before.active_recovery
            if active is None:
                return self._ignored_plan(
                    request, before, CooldownMutationReason.NO_ACTIVE_RECOVERY
                )
            if (
                isinstance(request, ReduceRemainingCooldownRequest)
                and request.reduction_frames == 0
            ):
                return self._ignored_plan(request, before, CooldownMutationReason.NO_EFFECT)
            if fact_kind is CooldownFactKind.RESET:
                ready_frame = request.frame
            else:
                assert isinstance(request, ReduceRemainingCooldownRequest)
                ready_frame = max(request.frame, active.ready_frame - request.reduction_frames)
            changed_active = replace(
                active, ready_frame=ready_frame, interval_frames=ready_frame - active.started_frame
            )
            intermediate = replace(
                before,
                active_recovery=changed_active,
                revision=before.revision + 1,
                last_changed_frame=request.frame,
            )
            facts = [self._fact(fact_kind, request, before, intermediate, active.duration_audit)]
            after = intermediate
            if ready_frame == request.frame:
                after, recovery_facts = self._complete_active(after, request.frame, request, True)
                facts.extend(recovery_facts)
            return CooldownMutationPlan(
                request.request_id,
                request.key,
                self.store.version,
                before.revision,
                before,
                after,
                tuple(facts),
                active.duration_audit,
            )

    def _ignored_plan(
        self,
        request: ReduceRemainingCooldownRequest | ResetActiveCooldownRequest,
        before: CooldownRecord,
        reason: CooldownMutationReason,
    ) -> CooldownMutationPlan:
        return CooldownMutationPlan(
            request.request_id,
            request.key,
            self.store.version,
            before.revision,
            before,
            before,
            (),
            ignored_reason=reason,
        )

    def _normalize_record(
        self, before: CooldownRecord, frame: int, operation_id: str
    ) -> tuple[CooldownRecord, list[CooldownFact]]:
        current = before
        facts: list[CooldownFact] = []
        while current.active_recovery is not None and current.active_recovery.ready_frame <= frame:
            ready_frame = current.active_recovery.ready_frame
            current, recovered = self._complete_active(current, ready_frame, operation_id, False)
            facts.extend(recovered)
        return current, facts

    def _complete_active(
        self,
        before: CooldownRecord,
        frame: int,
        source: StartCooldownRequest
        | ReduceRemainingCooldownRequest
        | ResetActiveCooldownRequest
        | str,
        restart_at_current_frame: bool,
    ) -> tuple[CooldownRecord, list[CooldownFact]]:
        active = before.active_recovery
        assert active is not None
        source_ref = source if isinstance(source, str) else source.source_ref
        operation_id = source if isinstance(source, str) else source.request_id
        start = frame if restart_at_current_frame else active.ready_frame
        if before.queued_recoveries:
            next_interval = active.duration_audit.resolved_duration_frames
            next_active = ActiveRecovery(
                started_frame=start,
                ready_frame=start + next_interval,
                interval_frames=next_interval,
                chain_id=active.chain_id,
                start_source_ref=active.start_source_ref,
                duration_audit=active.duration_audit,
            )
            after = replace(
                before,
                available_charges=before.available_charges + 1,
                active_recovery=next_active,
                queued_recoveries=before.queued_recoveries - 1,
                revision=before.revision + 1,
                last_changed_frame=frame,
            )
            return after, [
                self._fact(
                    CooldownFactKind.CHARGE_RECOVERED, source, before, after, active.duration_audit
                )
            ]
        after = replace(
            before,
            available_charges=before.available_charges + 1,
            active_recovery=None,
            revision=before.revision + 1,
            last_changed_frame=frame,
        )
        return after, [
            self._fact(
                CooldownFactKind.CHARGE_RECOVERED, source, before, after, active.duration_audit
            ),
            CooldownFact(
                fact_id=(
                    f"{operation_id}:{before.key.subject.subject_id}:"
                    f"{before.key.ability_key}:{before.revision}:chain_completed"
                ),
                fact_kind=CooldownFactKind.CHAIN_COMPLETED,
                frame=frame,
                key=before.key,
                operation_id=operation_id,
                chain_id=active.chain_id,
                before_available_charges=before.available_charges,
                after_available_charges=after.available_charges,
                active_ready_frame=None,
                queued_recoveries=after.queued_recoveries,
                source_ref=source_ref,
                duration_audit=active.duration_audit,
                before_record=before,
                after_record=after,
            ),
        ]

    def _fact(self, kind, source, before, after, resolution) -> CooldownFact:
        operation_id = source if isinstance(source, str) else source.request_id
        source_ref = source if isinstance(source, str) else source.source_ref
        active = after.active_recovery
        return CooldownFact(
            fact_id=(
                f"{operation_id}:{before.key.subject.subject_id}:"
                f"{before.key.ability_key}:{before.revision}:{kind.value}"
            ),
            fact_kind=kind,
            frame=after.last_changed_frame,
            key=after.key,
            operation_id=operation_id,
            chain_id=None if active is None else active.chain_id,
            before_available_charges=before.available_charges,
            after_available_charges=after.available_charges,
            active_ready_frame=None if active is None else active.ready_frame,
            queued_recoveries=after.queued_recoveries,
            source_ref=source_ref,
            duration_audit=resolution,
            before_record=before,
            after_record=after,
        )

    @staticmethod
    def _result(plan: CooldownMutationPlan) -> CooldownMutationResult:
        return CooldownMutationResult(
            plan.request_id,
            plan.key,
            plan.ignored_reason is None,
            plan.ignored_reason,
            plan.before,
            plan.after,
            tuple(sorted(plan.facts, key=lambda item: item.sort_key)),
            plan.resolution,
            plan.reused_chain_resolution,
        )

    def _assert_not_regressed(self, frame: int) -> None:
        if frame < self.normalized_through_frame:
            raise CooldownFrameRegressionError(
                f"冷却 frame 回退：{frame} < {self.normalized_through_frame}"
            )

    def _require_normalized(self, frame: int) -> None:
        self._assert_not_regressed(frame)
        if frame > self.normalized_through_frame:
            raise CooldownNotNormalizedError(
                f"冷却尚未规范化到 frame={frame}，当前为 {self.normalized_through_frame}"
            )

    @contextmanager
    def _mutation_scope(self) -> Iterator[None]:
        if self._mutation_active:
            if self._batch_preparing:
                yield
                return
            raise CooldownReentrancyError("冷却写入期间不允许同步重入")
        self._mutation_active = True
        try:
            yield
        finally:
            self._mutation_active = False
