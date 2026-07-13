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
    DamageAppliedPayload,
    EventEngine,
    EventType,
    GameEvent,
    ShieldAbsorptionResolvedPayload,
    ShieldCapacityChangedPayload,
    ShieldGrantedPayload,
    ShieldRemovedPayload,
)
from genshin_sim.core.mechanics import (
    CreateMechanicInstanceCommand,
    MechanicRemovalRecord,
    MechanicRuntime,
    RefreshMechanicExpiryCommand,
    RemoveMechanicInstanceCommand,
)
from genshin_sim.core.simulation import TeamRuntimeState
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.core.systems.health import CharacterDamageApplication, HealthRuntime
from genshin_sim.core.systems.shield.enums import (
    ShieldChangeReason,
    ShieldElement,
    ShieldGrantOutcome,
    ShieldGrantPolicy,
    ShieldProtectionKind,
    ShieldRemovalReason,
)
from genshin_sim.core.systems.shield.errors import (
    ShieldAttributeError,
    ShieldCapacityError,
    ShieldPolicyError,
    ShieldProtectionNotFoundError,
    ShieldStateConflictError,
    ShieldTargetMismatchError,
)
from genshin_sim.core.systems.shield.formulas import validate_shield_float
from genshin_sim.core.systems.shield.models import (
    CharacterIncomingDamage,
    IncomingDamageApplicationRecord,
    ShieldAbsorptionResult,
    ShieldCapacityChangeResult,
    ShieldComponent,
    ShieldGrantRequest,
    ShieldGrantResult,
    ShieldHitResult,
    ShieldRemovalResult,
    normalize_capacity_after,
)
from genshin_sim.core.systems.shield.resolver import ShieldResolver
from genshin_sim.core.systems.shield.store import (
    ShieldComponentStore,
    ShieldComponentUpdate,
)


class ShieldRuntime:
    """护盾授予、生命周期、并行吸收和生命提交编排入口。"""

    def __init__(
        self,
        resolver: ShieldResolver,
        mechanic_runtime: MechanicRuntime,
        component_store: ShieldComponentStore,
        attribute_resolver: AttributeResolver,
        health_runtime: HealthRuntime,
        event_engine: EventEngine,
        *,
        team_state: TeamRuntimeState | None = None,
    ) -> None:
        self.resolver = resolver
        self.mechanic_runtime = mechanic_runtime
        self.component_store = component_store
        self.attribute_resolver = attribute_resolver
        self.health_runtime = health_runtime
        self.event_engine = event_engine
        self.team_state = team_state
        self._mutation_active = False
        self._publishing_events = False
        self._pending_events: list[GameEvent] = []
        self._application_records: list[IncomingDamageApplicationRecord] = []
        self.mechanic_runtime.subscribe_removal(self._handle_mechanic_removed)

    @property
    def application_records(self) -> tuple[IncomingDamageApplicationRecord, ...]:
        return tuple(self._application_records)

    def grant(self, request: ShieldGrantRequest) -> ShieldGrantResult:
        with self._mutation_scope():
            return self._grant(request)

    def _grant(self, request: ShieldGrantRequest) -> ShieldGrantResult:
        resolution = self.resolver.resolve(request)
        candidates = self.component_store.conflicts(
            request.protection_ref,
            request.conflict_key,
            frame=request.frame,
            instance_store=self.mechanic_runtime.instance_store,
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
        instance_id: int,
        *,
        frame: int,
        reason: ShieldRemovalReason = ShieldRemovalReason.DISPELLED,
    ) -> ShieldRemovalResult:
        with self._mutation_scope():
            component = self.component_store.require(instance_id)
            self.mechanic_runtime.remove_instance(
                RemoveMechanicInstanceCommand(
                    instance_id=instance_id,
                    frame=frame,
                    reason=reason.value,
                )
            )
            return ShieldRemovalResult(
                frame=frame,
                instance_id=instance_id,
                mechanic_key=component.mechanic_key,
                protection_ref=component.protection_ref,
                reason=reason,
                native_remaining=component.remaining_native_absorption,
            )

    def absorb(self, incoming: CharacterIncomingDamage) -> ShieldAbsorptionResult:
        with self._mutation_scope():
            return self._absorb(incoming)

    def _absorb(self, incoming: CharacterIncomingDamage) -> ShieldAbsorptionResult:
        self._validate_incoming_target(incoming)
        active = self.component_store.active_for(
            incoming.protection_ref,
            frame=incoming.frame,
            instance_store=self.mechanic_runtime.instance_store,
        )
        if incoming.mitigated_amount == 0 or not active:
            return ShieldAbsorptionResult(
                damage_id=incoming.damage_id,
                frame=incoming.frame,
                protection_ref=incoming.protection_ref,
                target_ref=incoming.target_ref,
                mitigated_amount=incoming.mitigated_amount,
                element=incoming.element,
                active_character_shield_strength=0.0,
                shield_hits=(),
                protected_damage=0.0,
                health_bound_damage=incoming.mitigated_amount,
                had_active_shield_before=bool(active),
                has_active_shield_after=bool(active),
                depleted_instance_ids=(),
            )

        shield_strength = self._resolve_dynamic_shield_strength(incoming)
        strength_multiplier = validate_shield_float(
            1.0 + shield_strength,
            "shield_strength_multiplier",
        )
        if strength_multiplier <= 0:
            raise ShieldCapacityError("shield_strength_multiplier 必须是正数")

        version = self.component_store.version
        hits = tuple(
            self._calculate_hit(
                component,
                incoming,
                shield_strength=shield_strength,
                strength_multiplier=strength_multiplier,
            )
            for component in active
        )
        updates = tuple(
            ShieldComponentUpdate(
                instance_id=hit.instance_id,
                expected_remaining=hit.native_before,
                remaining_after=hit.native_after,
                maximum_after=self.component_store.require(
                    hit.instance_id
                ).maximum_native_absorption,
                remove_after=hit.depleted,
            )
            for hit in hits
        )
        self.component_store.apply_batch(updates, expected_version=version)

        depleted = tuple(hit.instance_id for hit in hits if hit.depleted)
        for instance_id in depleted:
            self.mechanic_runtime.remove_instance(
                RemoveMechanicInstanceCommand(
                    instance_id=instance_id,
                    frame=incoming.frame,
                    reason=ShieldRemovalReason.DEPLETED.value,
                )
            )

        protected_damage = max(
            (hit.absorbable_incoming_damage for hit in hits),
            default=0.0,
        )
        health_bound_damage = normalize_capacity_after(incoming.mitigated_amount - protected_damage)
        active_after = self.component_store.active_for(
            incoming.protection_ref,
            frame=incoming.frame,
            instance_store=self.mechanic_runtime.instance_store,
        )
        result = ShieldAbsorptionResult(
            damage_id=incoming.damage_id,
            frame=incoming.frame,
            protection_ref=incoming.protection_ref,
            target_ref=incoming.target_ref,
            mitigated_amount=incoming.mitigated_amount,
            element=incoming.element,
            active_character_shield_strength=shield_strength,
            shield_hits=hits,
            protected_damage=protected_damage,
            health_bound_damage=health_bound_damage,
            had_active_shield_before=True,
            has_active_shield_after=bool(active_after),
            depleted_instance_ids=depleted,
        )
        self._publish_absorption_events(active, hits, result)
        return result

    def apply_incoming_damage(
        self,
        incoming: CharacterIncomingDamage,
    ) -> IncomingDamageApplicationRecord:
        shield_result = self.absorb(incoming)
        health_application = CharacterDamageApplication(
            change_id=incoming.damage_id,
            frame=incoming.frame,
            target_ref=incoming.target_ref,
            amount=shield_result.health_bound_damage,
            source_ref=incoming.source_ref,
            source_context=incoming.source_context,
            tags=incoming.tags,
        )
        health_result = self.health_runtime.apply_damage(health_application)
        record = IncomingDamageApplicationRecord(
            incoming_damage=incoming,
            shield_result=shield_result,
            health_application=health_application,
            health_result=health_result,
        )
        self._application_records.append(record)
        self._emit_event(
            GameEvent(
                event_type=EventType.DAMAGE_APPLIED,
                frame=incoming.frame,
                payload=DamageAppliedPayload(record),
                source=self,
            )
        )
        return record

    def snapshot(self, frame: int):
        from genshin_sim.core.systems.shield.snapshots import ShieldSnapshot

        return ShieldSnapshot.from_runtime(self, frame)

    def _grant_replace(self, request, resolution, existing) -> ShieldGrantResult:
        replaced_instance_id = None
        if existing is not None:
            replaced_instance_id = existing.instance_id
            self.mechanic_runtime.remove_instance(
                RemoveMechanicInstanceCommand(
                    instance_id=existing.instance_id,
                    frame=request.frame,
                    reason=ShieldRemovalReason.REPLACED.value,
                )
            )
        outcome = (
            ShieldGrantOutcome.REPLACED
            if replaced_instance_id is not None
            else ShieldGrantOutcome.CREATED
        )
        return self._create_grant(
            request,
            resolution,
            outcome,
            replaced_instance_id=replaced_instance_id,
        )

    def _create_grant(
        self,
        request,
        resolution,
        outcome,
        *,
        replaced_instance_id=None,
    ) -> ShieldGrantResult:
        maximum = resolution.granted_absorption
        if request.grant_policy is ShieldGrantPolicy.ADD_CAPPED_REFRESH:
            if resolution.capacity_limit is None:
                raise ShieldPolicyError("add_capped_refresh 缺少 capacity_limit")
            maximum = resolution.capacity_limit
        remaining = min(resolution.granted_absorption, maximum)
        if remaining <= 0:
            raise ShieldCapacityError("新护盾容量必须是正数")
        instance = self.mechanic_runtime.create_instance(
            CreateMechanicInstanceCommand(
                capability_key="shield",
                mechanic_key=request.mechanic_key,
                handler_key=request.handler_key,
                owner_ref=request.protection_ref.to_key(),
                frame=request.frame,
                duration_frames=request.duration_frames,
            )
        )
        component = ShieldComponent(
            instance_id=instance.instance_id,
            mechanic_key=request.mechanic_key,
            handler_key=request.handler_key,
            protection_ref=request.protection_ref,
            creator_ref=request.creator_ref,
            source_context=request.source_context,
            element=request.element,
            maximum_native_absorption=maximum,
            remaining_native_absorption=remaining,
            conflict_key=request.conflict_key,
            grants_interruption_resistance=request.grants_interruption_resistance,
            grant_snapshot_ref=request.grant_id,
            tags=request.tags,
        )
        self.component_store.add(component)
        result = ShieldGrantResult(
            resolution=resolution,
            outcome=outcome,
            instance_id=instance.instance_id,
            replaced_instance_id=replaced_instance_id,
            remaining_before=0.0,
            remaining_after=remaining,
            maximum_after=maximum,
            expires_at_before=None,
            expires_at_after=instance.expires_at_frame,
        )
        self._publish_granted(result)
        return result

    def _refresh_grant(self, request, resolution, existing) -> ShieldGrantResult:
        instance = self.mechanic_runtime.instance_store.require_active(existing.instance_id)
        remaining_before = existing.remaining_native_absorption
        maximum_before = existing.maximum_native_absorption
        if request.grant_policy is ShieldGrantPolicy.REFRESH_REPLACE:
            remaining_after = resolution.granted_absorption
            maximum_after = resolution.granted_absorption
            outcome = ShieldGrantOutcome.REFRESHED
            reason = ShieldChangeReason.REFRESHED
        elif request.grant_policy is ShieldGrantPolicy.ADD_CAPPED_REFRESH:
            if resolution.capacity_limit is None:
                raise ShieldPolicyError("add_capped_refresh 缺少 capacity_limit")
            maximum_after = resolution.capacity_limit
            remaining_after = min(
                remaining_before + resolution.granted_absorption,
                maximum_after,
            )
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

        refreshed_component = replace(
            existing,
            creator_ref=request.creator_ref,
            source_context=request.source_context,
            element=request.element,
            maximum_native_absorption=maximum_after,
            remaining_native_absorption=remaining_after,
            grants_interruption_resistance=request.grants_interruption_resistance,
            grant_snapshot_ref=request.grant_id,
            tags=request.tags,
        )
        self.mechanic_runtime.refresh_expiry(
            RefreshMechanicExpiryCommand(
                instance_id=existing.instance_id,
                frame=request.frame,
                expires_at_frame=request.frame + request.duration_frames,
            )
        )
        self.component_store.replace(refreshed_component)
        result = ShieldGrantResult(
            resolution=resolution,
            outcome=outcome,
            instance_id=existing.instance_id,
            replaced_instance_id=None,
            remaining_before=remaining_before,
            remaining_after=remaining_after,
            maximum_after=maximum_after,
            expires_at_before=instance.expires_at_frame,
            expires_at_after=request.frame + request.duration_frames,
        )
        if remaining_before != remaining_after or maximum_before != maximum_after:
            self._publish_capacity_changed(
                ShieldCapacityChangeResult(
                    frame=request.frame,
                    instance_id=existing.instance_id,
                    mechanic_key=existing.mechanic_key,
                    protection_ref=existing.protection_ref,
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
        component: ShieldComponent,
        incoming: CharacterIncomingDamage,
        *,
        shield_strength: float,
        strength_multiplier: float,
    ) -> ShieldHitResult:
        element_multiplier = elemental_absorption_multiplier(
            component.element,
            incoming.element,
        )
        effective_multiplier = validate_shield_float(
            element_multiplier * strength_multiplier,
            "effective_multiplier",
        )
        if effective_multiplier <= 0:
            raise ShieldCapacityError("effective_multiplier 必须是正数")
        native_before = component.remaining_native_absorption
        native_cost = min(
            native_before,
            incoming.mitigated_amount / effective_multiplier,
        )
        native_after = normalize_capacity_after(native_before - native_cost)
        absorbable = min(
            incoming.mitigated_amount,
            native_before * effective_multiplier,
        )
        return ShieldHitResult(
            instance_id=component.instance_id,
            mechanic_key=component.mechanic_key,
            element=component.element,
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

    def _validate_incoming_target(self, incoming: CharacterIncomingDamage) -> None:
        protection = incoming.protection_ref
        if protection.kind is ShieldProtectionKind.ACTIVE_TEAM:
            if self.team_state is None:
                raise ShieldProtectionNotFoundError("active_team 缺少 TeamRuntimeState")
            current_ref = AttributeSubjectRef.character(
                self.team_state.current_character.combat_entity_id
            )
            if incoming.target_ref != current_ref:
                raise ShieldTargetMismatchError("active_team 来伤目标必须是当前场上角色")
            return
        if protection.kind is ShieldProtectionKind.CHARACTER:
            if incoming.target_ref.entity_id != protection.protection_id:
                raise ShieldTargetMismatchError("character protection ref 与来伤目标不一致")
            return
        raise ShieldProtectionNotFoundError(f"不支持的 protection ref：{protection}")

    def _resolve_dynamic_shield_strength(
        self,
        incoming: CharacterIncomingDamage,
    ) -> float:
        try:
            resolution = self.attribute_resolver.resolve(
                AttributeQuery(
                    subject_ref=incoming.target_ref,
                    attribute_key=BONUS_SHIELD_STRENGTH,
                    frame=incoming.frame,
                    context=AttributeQueryContext(
                        tags=incoming.tags,
                        source_ref=incoming.source_context,
                        target_ref=incoming.source_ref,
                    ),
                ),
                options=AttributeResolveOptions(trace_level=TraceLevel.NONE),
            )
        except AttributeSystemError as exc:
            raise ShieldAttributeError(f"无法解析动态护盾强效：{exc}") from exc
        return validate_shield_float(
            resolution.final_value,
            "active_character_shield_strength",
        )

    def _publish_absorption_events(
        self,
        active: tuple[ShieldComponent, ...],
        hits: tuple[ShieldHitResult, ...],
        result: ShieldAbsorptionResult,
    ) -> None:
        by_id = {component.instance_id: component for component in active}
        for hit in hits:
            component = by_id[hit.instance_id]
            self._publish_capacity_changed(
                ShieldCapacityChangeResult(
                    frame=result.frame,
                    instance_id=hit.instance_id,
                    mechanic_key=hit.mechanic_key,
                    protection_ref=result.protection_ref,
                    reason=ShieldChangeReason.ABSORBED,
                    native_before=hit.native_before,
                    native_after=hit.native_after,
                    maximum_before=component.maximum_native_absorption,
                    maximum_after=component.maximum_native_absorption,
                )
            )
        for hit in hits:
            if not hit.depleted:
                continue
            component = by_id[hit.instance_id]
            self._publish_removed(
                ShieldRemovalResult(
                    frame=result.frame,
                    instance_id=hit.instance_id,
                    mechanic_key=hit.mechanic_key,
                    protection_ref=result.protection_ref,
                    reason=ShieldRemovalReason.DEPLETED,
                    native_remaining=0.0,
                )
            )
        self._emit_event(
            GameEvent(
                event_type=EventType.SHIELD_ABSORPTION_RESOLVED,
                frame=result.frame,
                payload=ShieldAbsorptionResolvedPayload(result),
                source=self,
            )
        )

    def _handle_mechanic_removed(self, record: MechanicRemovalRecord) -> None:
        if record.instance.capability_key != "shield":
            return
        component = self.component_store.discard(record.instance_id)
        if component is None:
            return
        try:
            reason = ShieldRemovalReason(record.reason)
        except ValueError as exc:
            raise ShieldPolicyError(
                f"护盾实例使用了不支持的 removal reason：{record.reason}"
            ) from exc
        self._publish_removed(
            ShieldRemovalResult(
                frame=record.frame,
                instance_id=record.instance_id,
                mechanic_key=component.mechanic_key,
                protection_ref=component.protection_ref,
                reason=reason,
                native_remaining=component.remaining_native_absorption,
            )
        )

    def _publish_granted(self, result: ShieldGrantResult) -> None:
        self._emit_event(
            GameEvent(
                event_type=EventType.SHIELD_GRANTED,
                frame=result.resolution.frame,
                payload=ShieldGrantedPayload(result),
                source=self,
            )
        )

    def _publish_capacity_changed(self, result: ShieldCapacityChangeResult) -> None:
        self._emit_event(
            GameEvent(
                event_type=EventType.SHIELD_CAPACITY_CHANGED,
                frame=result.frame,
                payload=ShieldCapacityChangedPayload(result),
                source=self,
            )
        )

    def _publish_removed(self, result: ShieldRemovalResult) -> None:
        self._emit_event(
            GameEvent(
                event_type=EventType.SHIELD_REMOVED,
                frame=result.frame,
                payload=ShieldRemovedPayload(result),
                source=self,
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
