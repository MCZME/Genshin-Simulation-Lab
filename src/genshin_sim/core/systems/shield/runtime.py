from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace

from genshin_sim.core.attributes import (
    BONUS_SHIELD_STRENGTH,
    AttributeQuery,
    AttributeQueryContext,
    AttributeResolveOptions,
    AttributeResolver,
    AttributeSubjectRef,
    AttributeSystemError,
    TraceLevel,
)
from genshin_sim.core.events import (
    EventEngine,
    EventType,
    GameEvent,
    ShieldAbsorptionResolvedPayload,
    ShieldCapacityChangedPayload,
    ShieldGrantedPayload,
    ShieldRemovedPayload,
)
from genshin_sim.core.simulation import TeamRuntimeState
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.core.systems.shield.enums import (
    ShieldChangeReason,
    ShieldElement,
    ShieldGrantOutcome,
    ShieldGrantPolicy,
    ShieldLifecycleState,
    ShieldProtectionKind,
    ShieldRemovalReason,
)
from genshin_sim.core.systems.shield.errors import (
    ShieldAttributeError,
    ShieldCapacityError,
    ShieldPolicyError,
    ShieldStateConflictError,
)
from genshin_sim.core.systems.shield.formulas import validate_shield_float
from genshin_sim.core.systems.shield.models import (
    ShieldAbsorptionPlan,
    ShieldAbsorptionRequest,
    ShieldAbsorptionResult,
    ShieldCapacityChangeResult,
    ShieldCommitReceipt,
    ShieldGrantRequest,
    ShieldGrantResult,
    ShieldHitResult,
    ShieldInstanceRef,
    ShieldMutationPlan,
    ShieldRecord,
    ShieldRemovalResult,
    ShieldState,
    normalize_capacity_after,
)
from genshin_sim.core.systems.shield.resolver import ShieldResolver
from genshin_sim.core.systems.shield.store import ShieldStore


class ShieldRuntime:
    """护盾完整聚合、领域计划与领域事实入口。"""

    def __init__(
        self,
        resolver: ShieldResolver,
        shield_store: ShieldStore,
        attribute_resolver: AttributeResolver,
        event_engine: EventEngine,
        *,
        team_state: TeamRuntimeState | None = None,
    ) -> None:
        self.resolver = resolver
        self.shield_store = shield_store
        self.attribute_resolver = attribute_resolver
        self.event_engine = event_engine
        self.team_state = team_state
        self._mutation_active = False
        self._publishing_events = False
        self._pending_events: list[GameEvent] = []

    def grant(self, request: ShieldGrantRequest) -> ShieldGrantResult:
        with self._mutation_scope():
            resolution = self.resolver.resolve(request)
            candidates = self.shield_store.conflicts(
                request.protection_ref,
                request.conflict_key,
                frame=request.frame,
            )
            if len(candidates) > 1:
                raise ShieldStateConflictError(
                    f"conflict_key {request.conflict_key!r} 存在多个活动实例"
                )
            existing = candidates[0] if candidates else None
            if request.grant_policy is ShieldGrantPolicy.REPLACE:
                return self._grant_replace(request, resolution, existing)
            if request.grant_policy is ShieldGrantPolicy.COEXIST:
                if existing is not None:
                    raise ShieldStateConflictError(
                        "coexist 第一版不允许同一 conflict_key 存在多个活动实例"
                    )
                return self._create_grant(request, resolution, ShieldGrantOutcome.CREATED)
            if existing is None:
                return self._create_grant(request, resolution, ShieldGrantOutcome.CREATED)
            if (
                existing.mechanic_key != request.mechanic_key
                or existing.handler_key != request.handler_key
            ):
                raise ShieldStateConflictError(
                    "刷新策略要求活动实例使用相同 mechanic_key 和 handler_key"
                )
            return self._refresh_grant(request, resolution, existing)

    def remove(
        self,
        instance_ref: ShieldInstanceRef,
        *,
        frame: int,
        reason: ShieldRemovalReason = ShieldRemovalReason.DISPELLED,
    ) -> ShieldRemovalResult:
        with self._mutation_scope():
            record = self.shield_store.require(instance_ref)
            if not record.is_active_at(frame):
                raise ShieldStateConflictError("只有当前帧活动的护盾可以显式移除")
            removed = self._removed_record(record, frame, reason)
            self._commit_records(
                operation_id=f"shield-remove:{instance_ref.sequence}:{frame}:{reason.value}",
                frame=frame,
                expected=(record,),
                replacements=(removed,),
            )
            result = self._removal_result(removed)
            self._publish_removed(result)
            return result

    def prepare_absorption(self, request: ShieldAbsorptionRequest) -> ShieldAbsorptionPlan:
        if self._mutation_active or self._publishing_events:
            raise ShieldStateConflictError("护盾提交或事实发布期间不允许准备新计划")
        active = tuple(
            record
            for record in self.shield_store.records
            if record.is_active_at(request.frame)
            and self._protects_target(record, request.target_ref)
        )
        matched_refs = tuple(
            sorted(
                {record.state.protection_ref for record in active}, key=lambda item: item.to_key()
            )
        )
        if request.incoming_amount == 0 or not active:
            result = ShieldAbsorptionResult(
                damage_id=request.damage_id,
                frame=request.frame,
                target_ref=request.target_ref,
                incoming_amount=request.incoming_amount,
                element=request.element,
                matched_protection_refs=matched_refs,
                active_character_shield_strength=0.0,
                shield_hits=(),
                protected_damage=0.0,
                health_bound_damage=request.incoming_amount,
                had_active_shield_before=bool(active),
                has_active_shield_after=bool(active),
                depleted_instance_refs=(),
            )
            return ShieldAbsorptionPlan(
                damage_id=request.damage_id,
                frame=request.frame,
                target_ref=request.target_ref,
                operation_id=self._operation_id(request),
                expected_store_version=self.shield_store.version,
                expected_records=(),
                replacement_records=(),
                result=result,
                capacity_changes=(),
                removals=(),
            )

        shield_strength = self._resolve_dynamic_shield_strength(request)
        strength_multiplier = validate_shield_float(
            1.0 + shield_strength,
            "shield_strength_multiplier",
        )
        if strength_multiplier <= 0:
            raise ShieldCapacityError("shield_strength_multiplier 必须是正数")
        hits = tuple(
            self._calculate_hit(
                record,
                request,
                shield_strength=shield_strength,
                strength_multiplier=strength_multiplier,
            )
            for record in active
        )
        replacements = []
        capacity_changes = []
        removals = []
        by_ref = {record.instance_ref: record for record in active}
        for hit in hits:
            record = by_ref[hit.instance_ref]
            state = replace(record.state, remaining_native_absorption=hit.native_after)
            if hit.depleted:
                replacement = replace(
                    record,
                    lifecycle_state=ShieldLifecycleState.REMOVED,
                    state=state,
                    removed_frame=request.frame,
                    removal_reason=ShieldRemovalReason.DEPLETED,
                )
            else:
                replacement = replace(record, state=state)
            replacements.append(replacement)
            capacity_changes.append(
                ShieldCapacityChangeResult(
                    frame=request.frame,
                    instance_ref=record.instance_ref,
                    mechanic_key=record.mechanic_key,
                    protection_ref=record.state.protection_ref,
                    reason=ShieldChangeReason.ABSORBED,
                    native_before=hit.native_before,
                    native_after=hit.native_after,
                    maximum_before=record.state.maximum_native_absorption,
                    maximum_after=record.state.maximum_native_absorption,
                )
            )
            if hit.depleted:
                removals.append(self._removal_result(replacement))

        protected_damage = max(
            (hit.absorbable_incoming_damage for hit in hits),
            default=0.0,
        )
        health_bound_damage = normalize_capacity_after(request.incoming_amount - protected_damage)
        result = ShieldAbsorptionResult(
            damage_id=request.damage_id,
            frame=request.frame,
            target_ref=request.target_ref,
            incoming_amount=request.incoming_amount,
            element=request.element,
            matched_protection_refs=matched_refs,
            active_character_shield_strength=shield_strength,
            shield_hits=hits,
            protected_damage=protected_damage,
            health_bound_damage=health_bound_damage,
            had_active_shield_before=True,
            has_active_shield_after=any(not hit.depleted for hit in hits),
            depleted_instance_refs=tuple(hit.instance_ref for hit in hits if hit.depleted),
        )
        return ShieldAbsorptionPlan(
            damage_id=request.damage_id,
            frame=request.frame,
            target_ref=request.target_ref,
            operation_id=self._operation_id(request),
            expected_store_version=self.shield_store.version,
            expected_records=active,
            replacement_records=tuple(replacements),
            result=result,
            capacity_changes=tuple(capacity_changes),
            removals=tuple(removals),
        )

    def validate(self, plan: ShieldAbsorptionPlan) -> None:
        self.shield_store.validate(plan)

    def commit_prevalidated(self, plan: ShieldAbsorptionPlan) -> ShieldCommitReceipt:
        self.shield_store.commit_prevalidated(plan)
        return ShieldCommitReceipt(plan)

    def events_for(self, receipt: ShieldCommitReceipt) -> tuple[GameEvent, ...]:
        plan = receipt.plan
        events = [
            GameEvent(
                event_type=EventType.SHIELD_CAPACITY_CHANGED,
                frame=item.frame,
                payload=ShieldCapacityChangedPayload(item),
                source=self,
            )
            for item in plan.capacity_changes
        ]
        events.extend(
            GameEvent(
                event_type=EventType.SHIELD_REMOVED,
                frame=item.frame,
                payload=ShieldRemovedPayload(item),
                source=self,
            )
            for item in plan.removals
        )
        if plan.result.incoming_amount > 0 and plan.result.shield_hits:
            events.append(
                GameEvent(
                    event_type=EventType.SHIELD_ABSORPTION_RESOLVED,
                    frame=plan.frame,
                    payload=ShieldAbsorptionResolvedPayload(plan.result),
                    source=self,
                )
            )
        return tuple(events)

    def absorb(self, request: ShieldAbsorptionRequest) -> ShieldAbsorptionResult:
        plan = self.prepare_absorption(request)
        with self._mutation_scope():
            self.validate(plan)
            receipt = self.commit_prevalidated(plan)
            for event in self.events_for(receipt):
                self._emit_event(event)
            return plan.result

    def snapshot(self, frame: int):
        from genshin_sim.core.systems.shield.snapshots import ShieldSnapshot

        return ShieldSnapshot.from_runtime(self, frame)

    def update_frame(self, context, frame: int) -> None:
        del context
        with self._mutation_scope():
            due = self.shield_store.due_at(frame)
            for record in due:
                expired = self._removed_record(record, frame, ShieldRemovalReason.EXPIRED)
                expired = replace(expired, lifecycle_state=ShieldLifecycleState.EXPIRED)
                self._commit_records(
                    operation_id=f"shield-expire:{record.instance_ref.sequence}:{frame}",
                    frame=frame,
                    expected=(record,),
                    replacements=(expired,),
                )
                self._publish_removed(self._removal_result(expired))

    def is_idle(self) -> bool:
        return True

    def _grant_replace(self, request, resolution, existing) -> ShieldGrantResult:
        replaced_ref = None
        if existing is not None:
            replaced_ref = existing.instance_ref
        outcome = (
            ShieldGrantOutcome.REPLACED if replaced_ref is not None else ShieldGrantOutcome.CREATED
        )
        return self._create_grant(
            request,
            resolution,
            outcome,
            replaced_instance_ref=replaced_ref,
            replaced_record=existing,
        )

    def _create_grant(
        self,
        request,
        resolution,
        outcome,
        *,
        replaced_instance_ref=None,
        replaced_record=None,
    ) -> ShieldGrantResult:
        maximum = resolution.granted_absorption
        if request.grant_policy is ShieldGrantPolicy.ADD_CAPPED_REFRESH:
            if resolution.capacity_limit is None:
                raise ShieldPolicyError("add_capped_refresh 缺少 capacity_limit")
            maximum = resolution.capacity_limit
        remaining = min(resolution.granted_absorption, maximum)
        if remaining <= 0:
            raise ShieldCapacityError("新护盾容量必须是正数")
        ref = self.shield_store.allocate_ref()
        record = ShieldRecord(
            instance_ref=ref,
            mechanic_key=request.mechanic_key,
            handler_key=request.handler_key,
            created_frame=request.frame,
            expires_at_frame=request.frame + request.duration_frames,
            lifecycle_state=ShieldLifecycleState.ACTIVE,
            state=ShieldState(
                protection_ref=request.protection_ref,
                creator_ref=request.creator_ref,
                source_context=request.source_context,
                element=request.element,
                maximum_native_absorption=maximum,
                remaining_native_absorption=remaining,
                conflict_key=request.conflict_key,
                grant_snapshot_ref=request.grant_id,
                tags=request.tags,
            ),
        )
        replacements = [record]
        expected = ()
        removed = None
        if replaced_record is not None:
            removed = self._removed_record(
                replaced_record,
                request.frame,
                ShieldRemovalReason.REPLACED,
            )
            expected = (replaced_record,)
            replacements.append(removed)
        self._commit_records(
            operation_id=f"shield-grant:{request.grant_id}:{request.frame}",
            frame=request.frame,
            expected=expected,
            replacements=tuple(replacements),
        )
        result = ShieldGrantResult(
            resolution=resolution,
            outcome=outcome,
            instance_ref=ref,
            replaced_instance_ref=replaced_instance_ref,
            remaining_before=0.0,
            remaining_after=remaining,
            maximum_after=maximum,
            expires_at_before=None,
            expires_at_after=record.expires_at_frame,
        )
        if removed is not None:
            self._publish_removed(self._removal_result(removed))
        self._publish_granted(result)
        return result

    def _refresh_grant(self, request, resolution, existing: ShieldRecord) -> ShieldGrantResult:
        state = existing.state
        remaining_before = state.remaining_native_absorption
        maximum_before = state.maximum_native_absorption
        if request.grant_policy is ShieldGrantPolicy.REFRESH_REPLACE:
            remaining_after = resolution.granted_absorption
            maximum_after = resolution.granted_absorption
            outcome = ShieldGrantOutcome.REFRESHED
            reason = ShieldChangeReason.REFRESHED
        elif request.grant_policy is ShieldGrantPolicy.ADD_CAPPED_REFRESH:
            if resolution.capacity_limit is None:
                raise ShieldPolicyError("add_capped_refresh 缺少 capacity_limit")
            maximum_after = resolution.capacity_limit
            remaining_after = min(remaining_before + resolution.granted_absorption, maximum_after)
            outcome = ShieldGrantOutcome.STACKED
            reason = ShieldChangeReason.STACKED
        elif request.grant_policy is ShieldGrantPolicy.KEEP_STRONGER_REFRESH:
            remaining_after = max(remaining_before, resolution.granted_absorption)
            maximum_after = max(maximum_before, resolution.granted_absorption)
            outcome = (
                ShieldGrantOutcome.KEPT_EXISTING
                if remaining_before >= resolution.granted_absorption
                else ShieldGrantOutcome.REFRESHED
            )
            reason = ShieldChangeReason.REFRESHED
        else:
            raise ShieldPolicyError(f"不支持的刷新策略：{request.grant_policy.value}")
        refreshed = replace(
            existing,
            expires_at_frame=request.frame + request.duration_frames,
            state=replace(
                state,
                creator_ref=request.creator_ref,
                source_context=request.source_context,
                element=request.element,
                maximum_native_absorption=maximum_after,
                remaining_native_absorption=remaining_after,
                grant_snapshot_ref=request.grant_id,
                tags=request.tags,
            ),
        )
        self._commit_records(
            operation_id=f"shield-refresh:{request.grant_id}:{request.frame}",
            frame=request.frame,
            expected=(existing,),
            replacements=(refreshed,),
        )
        result = ShieldGrantResult(
            resolution=resolution,
            outcome=outcome,
            instance_ref=existing.instance_ref,
            replaced_instance_ref=None,
            remaining_before=remaining_before,
            remaining_after=remaining_after,
            maximum_after=maximum_after,
            expires_at_before=existing.expires_at_frame,
            expires_at_after=refreshed.expires_at_frame,
        )
        if remaining_before != remaining_after or maximum_before != maximum_after:
            self._publish_capacity_changed(
                ShieldCapacityChangeResult(
                    frame=request.frame,
                    instance_ref=existing.instance_ref,
                    mechanic_key=existing.mechanic_key,
                    protection_ref=state.protection_ref,
                    reason=reason,
                    native_before=remaining_before,
                    native_after=remaining_after,
                    maximum_before=maximum_before,
                    maximum_after=maximum_after,
                )
            )
        self._publish_granted(result)
        return result

    def _calculate_hit(
        self,
        record: ShieldRecord,
        request: ShieldAbsorptionRequest,
        *,
        shield_strength: float,
        strength_multiplier: float,
    ) -> ShieldHitResult:
        state = record.state
        element_multiplier = elemental_absorption_multiplier(state.element, request.element)
        effective_multiplier = validate_shield_float(
            element_multiplier * strength_multiplier,
            "effective_multiplier",
        )
        if effective_multiplier <= 0:
            raise ShieldCapacityError("effective_multiplier 必须是正数")
        native_before = state.remaining_native_absorption
        native_cost = min(native_before, request.incoming_amount / effective_multiplier)
        native_after = normalize_capacity_after(native_before - native_cost)
        absorbable = min(request.incoming_amount, native_before * effective_multiplier)
        return ShieldHitResult(
            instance_ref=record.instance_ref,
            mechanic_key=record.mechanic_key,
            protection_ref=state.protection_ref,
            element=state.element,
            native_before=native_before,
            native_cost=native_cost,
            native_after=native_after,
            element_multiplier=element_multiplier,
            shield_strength=shield_strength,
            shield_strength_multiplier=strength_multiplier,
            effective_multiplier=effective_multiplier,
            absorbable_incoming_damage=absorbable,
            depleted=native_after == 0,
        )

    def _protects_target(self, record: ShieldRecord, target_ref: AttributeSubjectRef) -> bool:
        protection = record.state.protection_ref
        if protection.kind is ShieldProtectionKind.CHARACTER:
            return target_ref.entity_id == protection.protection_id
        if protection.kind is ShieldProtectionKind.ACTIVE_TEAM:
            if self.team_state is None:
                return False
            current_ref = AttributeSubjectRef.character(
                self.team_state.current_character.combat_entity_id
            )
            return target_ref == current_ref
        return False

    def _resolve_dynamic_shield_strength(self, request: ShieldAbsorptionRequest) -> float:
        try:
            resolution = self.attribute_resolver.resolve(
                AttributeQuery(
                    subject_ref=request.target_ref,
                    attribute_key=BONUS_SHIELD_STRENGTH,
                    frame=request.frame,
                    context=AttributeQueryContext(
                        tags=request.tags,
                        source_ref=request.source_context,
                        target_ref=request.source_ref,
                    ),
                ),
                options=AttributeResolveOptions(trace_level=TraceLevel.NONE),
            )
        except AttributeSystemError as exc:
            raise ShieldAttributeError(f"无法解析动态护盾强效：{exc}") from exc
        return validate_shield_float(resolution.final_value, "active_character_shield_strength")

    @staticmethod
    def _operation_id(request: ShieldAbsorptionRequest) -> str:
        return (
            f"shield-absorption:{request.damage_id}:{request.frame}:{request.target_ref.entity_id}"
        )

    def _commit_records(
        self,
        *,
        operation_id: str,
        frame: int,
        expected: tuple[ShieldRecord, ...],
        replacements: tuple[ShieldRecord, ...],
    ) -> None:
        plan = ShieldMutationPlan(
            operation_id=operation_id,
            frame=frame,
            expected_store_version=self.shield_store.version,
            expected_records=expected,
            replacement_records=replacements,
        )
        self.shield_store.validate(plan)
        self.shield_store.commit_prevalidated(plan)

    @staticmethod
    def _removed_record(
        record: ShieldRecord, frame: int, reason: ShieldRemovalReason
    ) -> ShieldRecord:
        return replace(
            record,
            lifecycle_state=ShieldLifecycleState.REMOVED,
            removed_frame=frame,
            removal_reason=reason,
        )

    @staticmethod
    def _removal_result(record: ShieldRecord) -> ShieldRemovalResult:
        assert record.removed_frame is not None
        assert record.removal_reason is not None
        return ShieldRemovalResult(
            frame=record.removed_frame,
            instance_ref=record.instance_ref,
            mechanic_key=record.mechanic_key,
            protection_ref=record.state.protection_ref,
            reason=record.removal_reason,
            native_remaining=record.state.remaining_native_absorption,
        )

    def _publish_granted(self, result: ShieldGrantResult) -> None:
        self._emit_event(
            GameEvent(
                EventType.SHIELD_GRANTED,
                result.resolution.frame,
                ShieldGrantedPayload(result),
                source=self,
            )
        )

    def _publish_capacity_changed(self, result: ShieldCapacityChangeResult) -> None:
        self._emit_event(
            GameEvent(
                EventType.SHIELD_CAPACITY_CHANGED,
                result.frame,
                ShieldCapacityChangedPayload(result),
                source=self,
            )
        )

    def _publish_removed(self, result: ShieldRemovalResult) -> None:
        self._emit_event(
            GameEvent(
                EventType.SHIELD_REMOVED, result.frame, ShieldRemovedPayload(result), source=self
            )
        )

    @contextmanager
    def _mutation_scope(self) -> Iterator[None]:
        if self._mutation_active or self._publishing_events:
            raise ShieldStateConflictError("护盾状态提交或事实事件发布期间不允许重入修改")
        self._mutation_active = True
        try:
            yield
        finally:
            self._mutation_active = False
            self._flush_pending_events()

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
            raise ShieldStateConflictError("护盾事实事件发布期间不允许递归发布")
        self._publishing_events = True
        try:
            for event in events:
                self.event_engine.publish(event)
        finally:
            self._publishing_events = False


def elemental_absorption_multiplier(
    shield_element: ShieldElement,
    damage_element: DamageElement,
) -> float:
    if shield_element is ShieldElement.GEO:
        return 1.5
    if shield_element is not ShieldElement.NONE and shield_element.value == damage_element.value:
        return 2.5
    return 1.0
