from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace

from genshin_sim.core.events import (
    BuffAppliedPayload,
    BuffRemovedPayload,
    EventEngine,
    EventType,
    GameEvent,
)
from genshin_sim.core.systems.buff.definitions import BuffDefinitionRegistry
from genshin_sim.core.systems.buff.enums import (
    BuffApplicationPolicy,
    BuffLifecycleState,
    BuffRemovalReason,
)
from genshin_sim.core.systems.buff.errors import (
    BuffInstanceNotFoundError,
    BuffReentrancyError,
    BuffValidationError,
)
from genshin_sim.core.systems.buff.models import (
    ApplyBuffRequest,
    BuffApplicationResult,
    BuffCommitReceipt,
    BuffMutationPlan,
    BuffRecord,
    BuffRemovalResult,
    RemoveBuffRequest,
    removal_result_from_record,
    validate_frame,
)
from genshin_sim.core.systems.buff.resolver import BuffResolver
from genshin_sim.core.systems.buff.store import BuffStore


class BuffRuntime:
    """状态效果计划、提交、生命周期和事实发布入口。"""

    def __init__(
        self,
        definition_registry: BuffDefinitionRegistry,
        resolver: BuffResolver,
        buff_store: BuffStore,
        event_engine: EventEngine,
    ) -> None:
        self.definition_registry = definition_registry
        self.resolver = resolver
        self.buff_store = buff_store
        self.event_engine = event_engine
        self._mutation_active = False
        self._publishing_events = False
        self._pending_events: list[GameEvent] = []

    def apply(self, request: ApplyBuffRequest) -> BuffApplicationResult:
        return self.apply_many((request,))[0]

    def apply_many(
        self,
        requests: Sequence[ApplyBuffRequest],
    ) -> tuple[BuffApplicationResult, ...]:
        with self._mutation_scope():
            plan = self._prepare_apply_unchecked(tuple(requests))
            self.validate(plan)
            receipt = self._commit_prevalidated_unchecked(plan)
            for event in self.events_for(receipt):
                self._emit_event(event)
            return plan.application_results

    def prepare_apply(self, requests: Sequence[ApplyBuffRequest]) -> BuffMutationPlan:
        self._ensure_can_write()
        return self._prepare_apply_unchecked(tuple(requests))

    def remove(self, request: RemoveBuffRequest) -> BuffRemovalResult:
        with self._mutation_scope():
            plan = self._prepare_remove_unchecked(request)
            self.validate(plan)
            receipt = self._commit_prevalidated_unchecked(plan)
            for event in self.events_for(receipt):
                self._emit_event(event)
            return plan.removal_results[0]

    def validate(self, plan: BuffMutationPlan) -> None:
        self.buff_store.validate(plan)

    def commit_prevalidated(self, plan: BuffMutationPlan) -> BuffCommitReceipt:
        with self._mutation_scope():
            return self._commit_prevalidated_unchecked(plan)

    def events_for(self, receipt: BuffCommitReceipt) -> tuple[GameEvent, ...]:
        plan = receipt.plan
        events: list[GameEvent] = []
        removals_by_ref = {
            result.instance_ref: result
            for result in plan.removal_results
            if result.reason is BuffRemovalReason.REPLACED
        }
        if plan.application_results:
            for result in plan.application_results:
                for replaced_ref in result.replaced_instance_refs:
                    removal = removals_by_ref[replaced_ref]
                    events.append(
                        GameEvent(
                            EventType.BUFF_REMOVED,
                            removal.frame,
                            BuffRemovedPayload(removal),
                            source=self,
                        )
                    )
                events.append(
                    GameEvent(
                        EventType.BUFF_APPLIED,
                        result.frame,
                        BuffAppliedPayload(result),
                        source=self,
                    )
                )
            return tuple(events)

        return tuple(
            GameEvent(
                EventType.BUFF_REMOVED,
                result.frame,
                BuffRemovedPayload(result),
                source=self,
            )
            for result in plan.removal_results
        )

    def publish_committed_facts(self, receipt: BuffCommitReceipt) -> None:
        """发布已提交计划的 Buff 事实，并保留事件期写入保护。"""

        self._publish_events(self.events_for(receipt))

    def update_frame(self, context, frame: int) -> None:
        del context
        validate_frame(frame)
        with self._mutation_scope():
            due = self.buff_store.due_at(frame)
            if not due:
                return
            replacements = tuple(
                replace(
                    record,
                    lifecycle_state=BuffLifecycleState.EXPIRED,
                    removed_frame=frame,
                    removal_reason=BuffRemovalReason.EXPIRED,
                )
                for record in due
            )
            plan = BuffMutationPlan(
                operation_id=_expire_operation_id(frame, due),
                frame=frame,
                expected_store_version=self.buff_store.version,
                request_ids=(),
                expected_records=due,
                replacement_records=replacements,
                application_results=(),
                removal_results=tuple(
                    removal_result_from_record(record) for record in replacements
                ),
            )
            self.validate(plan)
            receipt = self._commit_prevalidated_unchecked(plan)
            for event in self.events_for(receipt):
                self._emit_event(event)

    def snapshot(self, frame: int):
        from genshin_sim.core.systems.buff.snapshots import BuffSnapshot

        return BuffSnapshot.from_runtime(self, frame)

    def is_idle(self) -> bool:
        return True

    def _prepare_apply_unchecked(
        self,
        requests: tuple[ApplyBuffRequest, ...],
    ) -> BuffMutationPlan:
        if not requests:
            raise BuffValidationError("apply_many 至少需要一个请求")
        frames = {request.frame for request in requests}
        if len(frames) != 1:
            raise BuffValidationError("apply_many 要求同一批请求 frame 一致")
        orders = [request.order for request in requests]
        if len(orders) != len(set(orders)):
            raise BuffValidationError("apply_many 同一批请求 order 不能重复")
        request_ids = [request.request_id for request in requests]
        if len(request_ids) != len(set(request_ids)):
            raise BuffValidationError("apply_many 同一批请求 request_id 不能重复")

        ordered_requests = tuple(sorted(requests, key=lambda item: item.order))
        frame = ordered_requests[0].frame
        original_records_by_ref = {
            record.instance_ref: record for record in self.buff_store.records
        }
        working_records_by_ref = dict(original_records_by_ref)
        expected_by_ref: dict[object, BuffRecord] = {}
        replacement_by_ref: dict[object, BuffRecord] = {}
        application_results: list[BuffApplicationResult] = []
        removal_results: list[BuffRemovalResult] = []

        for request in ordered_requests:
            definition = self.definition_registry.get(request.definition_key)
            conflicts = _conflicts_from_records(
                tuple(working_records_by_ref.values()),
                target_ref=request.target_ref,
                conflict_key=definition.conflict_key,
                frame=request.frame,
            )
            if definition.application_policy is BuffApplicationPolicy.COEXIST:
                resolver_conflicts: tuple[BuffRecord, ...] = ()
            else:
                resolver_conflicts = conflicts
            allocated_ref = (
                self.buff_store.allocate_ref()
                if _requires_allocated_ref(definition.application_policy, resolver_conflicts)
                else None
            )
            resolution = self.resolver.resolve_apply(
                definition,
                request,
                resolver_conflicts,
                allocated_ref,
            )
            for expected in resolution.expected_records:
                original = original_records_by_ref.get(expected.instance_ref)
                if original is not None:
                    expected_by_ref.setdefault(expected.instance_ref, original)
            for replacement_record in resolution.replacement_records:
                working_records_by_ref[replacement_record.instance_ref] = replacement_record
                replacement_by_ref[replacement_record.instance_ref] = replacement_record
            application_results.append(resolution.result)
            removal_results.extend(resolution.removals)

        return BuffMutationPlan(
            operation_id=_apply_operation_id(
                frame,
                tuple(request.request_id for request in ordered_requests),
            ),
            frame=frame,
            expected_store_version=self.buff_store.version,
            request_ids=tuple(request.request_id for request in ordered_requests),
            expected_records=tuple(expected_by_ref.values()),
            replacement_records=tuple(replacement_by_ref.values()),
            application_results=tuple(application_results),
            removal_results=tuple(removal_results),
        )

    def _prepare_remove_unchecked(self, request: RemoveBuffRequest) -> BuffMutationPlan:
        record = self.buff_store.get(request.instance_ref)
        if record is None or not record.is_active_at(request.frame):
            raise BuffInstanceNotFoundError(
                f"请求 {request.request_id} 要移除的 Buff 不存在或不活动："
                f"{request.instance_ref.to_key()}"
            )
        removed = replace(
            record,
            lifecycle_state=BuffLifecycleState.REMOVED,
            removed_frame=request.frame,
            removal_reason=request.reason,
        )
        return BuffMutationPlan(
            operation_id=_remove_operation_id(request.request_id),
            frame=request.frame,
            expected_store_version=self.buff_store.version,
            request_ids=(request.request_id,),
            expected_records=(record,),
            replacement_records=(removed,),
            application_results=(),
            removal_results=(removal_result_from_record(removed),),
        )

    def _commit_prevalidated_unchecked(self, plan: BuffMutationPlan) -> BuffCommitReceipt:
        self.buff_store.commit_prevalidated(plan)
        return BuffCommitReceipt(plan)

    @contextmanager
    def _mutation_scope(self) -> Iterator[None]:
        self._ensure_can_write()
        self._mutation_active = True
        try:
            yield
        finally:
            self._mutation_active = False
            self._flush_pending_events()

    def _ensure_can_write(self) -> None:
        if self._mutation_active or self._publishing_events:
            raise BuffReentrancyError("Buff 状态提交或事实发布期间不允许重入写入")

    def _emit_event(self, event: GameEvent) -> None:
        if self._mutation_active:
            self._pending_events.append(event)
            return
        self._publish_events((event,))

    def _flush_pending_events(self) -> None:
        events = tuple(self._pending_events)
        self._pending_events.clear()
        if events:
            self._publish_events(events)

    def _publish_events(self, events: tuple[GameEvent, ...]) -> None:
        if self._publishing_events:
            raise BuffReentrancyError("Buff 事实事件发布期间不允许递归发布")
        self._publishing_events = True
        try:
            for event in events:
                self.event_engine.publish(event)
        finally:
            self._publishing_events = False


def _requires_allocated_ref(
    policy: BuffApplicationPolicy,
    conflicts: tuple[BuffRecord, ...],
) -> bool:
    return policy in {BuffApplicationPolicy.REPLACE, BuffApplicationPolicy.COEXIST} or not conflicts


def _conflicts_from_records(
    records: tuple[BuffRecord, ...],
    *,
    target_ref,
    conflict_key: str,
    frame: int,
) -> tuple[BuffRecord, ...]:
    return tuple(
        sorted(
            (
                record
                for record in records
                if record.is_active_at(frame)
                and record.state.target_ref == target_ref
                and record.definition.conflict_key == conflict_key
            ),
            key=lambda item: item.instance_ref,
        )
    )


def _apply_operation_id(frame: int, request_ids: tuple[str, ...]) -> str:
    return f"buff-apply:{frame}{_length_prefixed(request_ids)}"


def _remove_operation_id(request_id: str) -> str:
    return f"buff-remove{_length_prefixed((request_id,))}"


def _expire_operation_id(frame: int, records: tuple[BuffRecord, ...]) -> str:
    sequences = tuple(str(record.instance_ref.sequence) for record in records)
    return f"buff-expire:{frame}{_length_prefixed(sequences)}"


def _length_prefixed(values: tuple[str, ...]) -> str:
    return "".join(f":{len(value)}:{value}" for value in values)
