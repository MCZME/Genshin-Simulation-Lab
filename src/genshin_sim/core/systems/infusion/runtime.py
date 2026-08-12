from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import Element
from genshin_sim.core.events import (
    EventEngine,
    EventType,
    GameEvent,
    InfusionAppliedPayload,
    InfusionRemovedPayload,
)
from genshin_sim.core.systems.infusion.definitions import InfusionDefinitionRegistry
from genshin_sim.core.systems.infusion.enums import (
    InfusionApplicationOutcome,
    InfusionLifecycleState,
    InfusionMode,
    InfusionRemovalReason,
    RefreshPolicy,
)
from genshin_sim.core.systems.infusion.errors import (
    InfusionInstanceNotFoundError,
    InfusionReentrancyError,
    InfusionValidationError,
)
from genshin_sim.core.systems.infusion.models import (
    ApplyInfusionRequest,
    EffectiveElementResolution,
    InfusionApplicationResult,
    InfusionCommitReceipt,
    InfusionMutationPlan,
    InfusionRecord,
    InfusionRemovalResult,
    RemoveInfusionRequest,
    removal_result_from_record,
    validate_frame,
)
from genshin_sim.core.systems.infusion.resolver import (
    InfusionResolver,
    converge_application,
)
from genshin_sim.core.systems.infusion.snapshots import InfusionInstanceSnapshot
from genshin_sim.core.systems.infusion.store import InfusionStore


class InfusionRuntime:
    """附魔/转化计划、提交、生命周期、有效元素解析与事实发布入口。"""

    def __init__(
        self,
        definition_registry: InfusionDefinitionRegistry,
        resolver: InfusionResolver,
        infusion_store: InfusionStore,
        event_engine: EventEngine,
    ) -> None:
        self.definition_registry = definition_registry
        self.resolver = resolver
        self.infusion_store = infusion_store
        self.event_engine = event_engine
        self._mutation_active = False
        self._publishing_events = False
        self._pending_events: list[GameEvent] = []

    def apply(self, request: ApplyInfusionRequest) -> InfusionApplicationResult:
        return self.apply_many((request,))[0]

    def apply_many(
        self,
        requests: Sequence[ApplyInfusionRequest],
    ) -> tuple[InfusionApplicationResult, ...]:
        with self._mutation_scope():
            plan = self._prepare_apply_unchecked(tuple(requests))
            self.validate(plan)
            receipt = self._commit_prevalidated_unchecked(plan)
            for event in self.events_for(receipt):
                self._emit_event(event)
            return plan.application_results

    def prepare_apply(self, requests: Sequence[ApplyInfusionRequest]) -> InfusionMutationPlan:
        self._ensure_can_write()
        return self._prepare_apply_unchecked(tuple(requests))

    def remove(self, request: RemoveInfusionRequest) -> InfusionRemovalResult:
        with self._mutation_scope():
            plan = self._prepare_remove_unchecked(request)
            self.validate(plan)
            receipt = self._commit_prevalidated_unchecked(plan)
            for event in self.events_for(receipt):
                self._emit_event(event)
            return plan.removal_results[0]

    def validate(self, plan: InfusionMutationPlan) -> None:
        self.infusion_store.validate(plan)

    def commit_prevalidated(self, plan: InfusionMutationPlan) -> InfusionCommitReceipt:
        with self._mutation_scope():
            return self._commit_prevalidated_unchecked(plan)

    def resolve_effective_element(
        self,
        frame: int,
        character_ref: AttributeSubjectRef,
        base_element: Element,
        attack_tag: str | None = None,
    ) -> EffectiveElementResolution:
        active = self.infusion_store.active(frame, character_ref=character_ref)
        return self.resolver.resolve_effective_element(
            frame,
            character_ref,
            base_element,
            active,
            attack_tag=attack_tag,
        )

    def events_for(self, receipt: InfusionCommitReceipt) -> tuple[GameEvent, ...]:
        plan = receipt.plan
        events: list[GameEvent] = []
        for result in plan.removal_results:
            if result.reason is not InfusionRemovalReason.REPLACED:
                events.append(
                    GameEvent(
                        EventType.INFUSION_REMOVED,
                        result.frame,
                        InfusionRemovedPayload(result),
                        source=self,
                    )
                )
        for result in plan.application_results:
            for replaced_ref in result.replaced_instance_refs:
                removal = next(
                    item for item in plan.removal_results if item.instance_ref == replaced_ref
                )
                events.append(
                    GameEvent(
                        EventType.INFUSION_REMOVED,
                        removal.frame,
                        InfusionRemovedPayload(removal),
                        source=self,
                    )
                )
            events.append(
                GameEvent(
                    EventType.INFUSION_APPLIED,
                    result.frame,
                    InfusionAppliedPayload(_with_instance_after(self, result)),
                    source=self,
                )
            )
        for result in plan.removal_results:
            if result.reason is not InfusionRemovalReason.REPLACED:
                continue
            if any(
                result.instance_ref in item.replaced_instance_refs
                for item in plan.application_results
            ):
                continue
            events.append(
                GameEvent(
                    EventType.INFUSION_REMOVED,
                    result.frame,
                    InfusionRemovedPayload(result),
                    source=self,
                )
            )
        return tuple(events)

    def publish_committed_facts(self, receipt: InfusionCommitReceipt) -> None:
        """发布已提交计划的附魔事实，并保留事件期写入保护。"""

        self._publish_events(self.events_for(receipt))

    def update_frame(self, context, frame: int) -> None:
        del context
        validate_frame(frame)
        with self._mutation_scope():
            working = {record.instance_ref: record for record in self.infusion_store.records}
            expected_by_ref: dict[object, InfusionRecord] = {}
            replacement_by_ref: dict[object, InfusionRecord] = {}
            application_results: list[InfusionApplicationResult] = []
            removal_results: list[InfusionRemovalResult] = []

            refresh_due = tuple(
                sorted(
                    (
                        record
                        for record in working.values()
                        if record.lifecycle_state is InfusionLifecycleState.ACTIVE
                        and record.refresh_policy is RefreshPolicy.PERIODIC
                        and record.next_refresh_frame == frame
                    ),
                    key=lambda item: item.instance_ref,
                )
            )
            for order, record in enumerate(refresh_due):
                definition = record.definition
                refreshed = replace(
                    record,
                    last_applied_frame=frame,
                    expires_at_frame=frame + definition.duration_frames,
                    next_refresh_frame=(
                        frame + definition.period_frames
                        if definition.period_frames is not None
                        else None
                    ),
                    remaining_gauge=definition.weapon_gauge,
                    frozen=False,
                )
                active_others = tuple(
                    item
                    for item in working.values()
                    if item.is_active_at(frame) and item.instance_ref != record.instance_ref
                )
                converged = converge_application(active_others, refreshed)
                for converged_record in converged:
                    old = working.get(converged_record.instance_ref)
                    if old is not None:
                        expected_by_ref.setdefault(converged_record.instance_ref, old)
                    working[converged_record.instance_ref] = converged_record
                    replacement_by_ref[converged_record.instance_ref] = converged_record
                application_results.append(
                    InfusionApplicationResult(
                        request_id=f"infusion-periodic:{record.instance_ref.to_key()}:{frame}",
                        frame=frame,
                        order=order,
                        outcome=InfusionApplicationOutcome.REFRESHED,
                        instance_ref=refreshed.instance_ref,
                        definition_key=definition.definition_key,
                        mechanic_key=definition.mechanic_key,
                        mode=refreshed.mode,
                        element=refreshed.element,
                        character_ref=refreshed.character_ref,
                        applier_ref=refreshed.applier_ref,
                        source_context=refreshed.source_context,
                        expires_at_before=record.expires_at_frame,
                        expires_at_after=refreshed.expires_at_frame,
                        next_refresh_frame_after=refreshed.next_refresh_frame,
                    )
                )

            due = tuple(
                sorted(
                    (
                        record
                        for record in working.values()
                        if record.lifecycle_state is InfusionLifecycleState.ACTIVE
                        and record.expires_at_frame <= frame
                    ),
                    key=lambda item: item.instance_ref,
                )
            )
            for record in due:
                expired = _expired_record(record, frame)
                expected_by_ref.setdefault(record.instance_ref, record)
                working[record.instance_ref] = expired
                replacement_by_ref[record.instance_ref] = expired
                removal_results.append(removal_result_from_record(expired))

            if not replacement_by_ref:
                return
            plan = InfusionMutationPlan(
                operation_id=_frame_operation_id(frame, refresh_due, due),
                frame=frame,
                expected_store_version=self.infusion_store.version,
                request_ids=(),
                expected_records=tuple(expected_by_ref.values()),
                replacement_records=tuple(replacement_by_ref.values()),
                application_results=tuple(application_results),
                removal_results=tuple(removal_results),
            )
            self.validate(plan)
            receipt = self._commit_prevalidated_unchecked(plan)
            for event in self.events_for(receipt):
                self._emit_event(event)

    def snapshot(self, frame: int):
        from genshin_sim.core.systems.infusion.snapshots import InfusionSnapshot

        return InfusionSnapshot.from_runtime(self, frame)

    def is_idle(self) -> bool:
        return True

    def _prepare_apply_unchecked(
        self,
        requests: tuple[ApplyInfusionRequest, ...],
    ) -> InfusionMutationPlan:
        if not requests:
            raise InfusionValidationError("apply_many 至少需要一个请求")
        frames = {request.frame for request in requests}
        if len(frames) != 1:
            raise InfusionValidationError("apply_many 要求同一批请求 frame 一致")
        orders = [request.order for request in requests]
        if len(orders) != len(set(orders)):
            raise InfusionValidationError("apply_many 同一批请求 order 不能重复")
        request_ids = [request.request_id for request in requests]
        if len(request_ids) != len(set(request_ids)):
            raise InfusionValidationError("apply_many 同一批请求 request_id 不能重复")

        ordered_requests = tuple(sorted(requests, key=lambda item: item.order))
        frame = ordered_requests[0].frame
        original_records_by_ref = {
            record.instance_ref: record for record in self.infusion_store.records
        }
        working_records_by_ref = dict(original_records_by_ref)
        expected_by_ref: dict[object, InfusionRecord] = {}
        replacement_by_ref: dict[object, InfusionRecord] = {}
        application_results: list[InfusionApplicationResult] = []
        removal_results: list[InfusionRemovalResult] = []

        for request in ordered_requests:
            definition = self.definition_registry.get(request.definition_key)
            active = _active_from_records(
                tuple(working_records_by_ref.values()),
                character_ref=request.character_ref,
                frame=request.frame,
            )
            allocated_ref = (
                self.infusion_store.allocate_ref()
                if _requires_allocated_ref(definition, active)
                else None
            )
            resolution = self.resolver.resolve_apply(
                definition,
                request,
                active,
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

        return InfusionMutationPlan(
            operation_id=_apply_operation_id(
                frame,
                tuple(request.request_id for request in ordered_requests),
            ),
            frame=frame,
            expected_store_version=self.infusion_store.version,
            request_ids=tuple(request.request_id for request in ordered_requests),
            expected_records=tuple(expected_by_ref.values()),
            replacement_records=tuple(replacement_by_ref.values()),
            application_results=tuple(application_results),
            removal_results=tuple(removal_results),
        )

    def _prepare_remove_unchecked(self, request: RemoveInfusionRequest) -> InfusionMutationPlan:
        record = self.infusion_store.get(request.instance_ref)
        if record is None or not record.is_active_at(request.frame):
            raise InfusionInstanceNotFoundError(
                f"请求 {request.request_id} 要移除的附魔不存在或不活动："
                f"{request.instance_ref.to_key()}"
            )
        removed = _removed_record(record, request.frame, request.reason)
        return InfusionMutationPlan(
            operation_id=_remove_operation_id(request.request_id),
            frame=request.frame,
            expected_store_version=self.infusion_store.version,
            request_ids=(request.request_id,),
            expected_records=(record,),
            replacement_records=(removed,),
            application_results=(),
            removal_results=(removal_result_from_record(removed),),
        )

    def _commit_prevalidated_unchecked(self, plan: InfusionMutationPlan) -> InfusionCommitReceipt:
        self.infusion_store.commit_prevalidated(plan)
        return InfusionCommitReceipt(plan)

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
            raise InfusionReentrancyError("附魔状态提交或事实发布期间不允许重入写入")

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
            raise InfusionReentrancyError("附魔事实事件发布期间不允许递归发布")
        self._publishing_events = True
        try:
            for event in events:
                self.event_engine.publish(event)
        finally:
            self._publishing_events = False


def _requires_allocated_ref(
    definition,
    active: tuple[InfusionRecord, ...],
) -> bool:
    if definition.mode is InfusionMode.CONVERSION:
        return True
    same_definition = tuple(
        record
        for record in active
        if record.mode is InfusionMode.INFUSION
        and record.element == definition.element
        and record.definition.definition_key == definition.definition_key
    )
    return not same_definition


def _active_from_records(
    records: tuple[InfusionRecord, ...],
    *,
    character_ref,
    frame: int,
) -> tuple[InfusionRecord, ...]:
    return tuple(
        sorted(
            (
                record
                for record in records
                if record.is_active_at(frame) and record.character_ref == character_ref
            ),
            key=lambda item: item.instance_ref,
        )
    )


def _expired_record(record: InfusionRecord, frame: int) -> InfusionRecord:
    return replace(
        record,
        lifecycle_state=InfusionLifecycleState.EXPIRED,
        removed_frame=frame,
        removal_reason=InfusionRemovalReason.EXPIRED,
    )


def _removed_record(
    record: InfusionRecord,
    frame: int,
    reason: InfusionRemovalReason,
) -> InfusionRecord:
    return replace(
        record,
        lifecycle_state=InfusionLifecycleState.REMOVED,
        removed_frame=frame,
        removal_reason=reason,
    )


def _apply_operation_id(frame: int, request_ids: tuple[str, ...]) -> str:
    return f"infusion-apply:{frame}{_length_prefixed(request_ids)}"


def _remove_operation_id(request_id: str) -> str:
    return f"infusion-remove{_length_prefixed((request_id,))}"


def _frame_operation_id(
    frame: int,
    refresh_records: tuple[InfusionRecord, ...],
    expire_records: tuple[InfusionRecord, ...],
) -> str:
    refresh_sequences = tuple(str(record.instance_ref.sequence) for record in refresh_records)
    expire_sequences = tuple(str(record.instance_ref.sequence) for record in expire_records)
    return (
        f"infusion-frame:{frame}"
        f"{_length_prefixed(refresh_sequences)}"
        f"{_length_prefixed(expire_sequences)}"
    )


def _length_prefixed(values: tuple[str, ...]) -> str:
    return "".join(f":{len(value)}:{value}" for value in values)


def _with_instance_after(
    runtime: InfusionRuntime,
    result: InfusionApplicationResult,
) -> InfusionApplicationResult:
    """把已提交附魔实例的完整快照附加到应用结果，供事件载荷精确折叠。"""

    if result.instance_after is not None:
        return result
    record = next(
        item
        for item in runtime.infusion_store.records
        if item.instance_ref == result.instance_ref
    )
    return replace(result, instance_after=InfusionInstanceSnapshot.from_record(record))
