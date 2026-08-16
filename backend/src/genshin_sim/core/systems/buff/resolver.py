from __future__ import annotations

from dataclasses import dataclass, replace

from genshin_sim.core.systems.buff.definitions import BuffDefinition
from genshin_sim.core.systems.buff.enums import (
    BuffApplicationOutcome,
    BuffApplicationPolicy,
    BuffLifecycleState,
    BuffRemovalReason,
    BuffStackScaling,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.buff.errors import (
    BuffApplicationConflictError,
    BuffModifierBindingError,
    BuffValidationError,
)
from genshin_sim.core.systems.buff.models import (
    ApplyBuffRequest,
    BuffApplicationResult,
    BuffInstanceRef,
    BuffRecord,
    BuffRemovalResult,
    BuffResolvedAttributeModifier,
    BuffState,
)


def scaled_modifier_value(
    record: BuffRecord,
    resolved: BuffResolvedAttributeModifier,
) -> float:
    if resolved.template.stack_scaling is BuffStackScaling.CONSTANT:
        return resolved.value
    if resolved.template.stack_scaling is BuffStackScaling.LINEAR:
        return resolved.value * record.state.stack_count
    raise BuffModifierBindingError(
        f"Buff {record.definition.definition_key!r} stack_scaling 不受支持"
    )


@dataclass(frozen=True, slots=True)
class BuffApplicationResolution:
    definition: BuffDefinition
    request: ApplyBuffRequest
    expected_records: tuple[BuffRecord, ...]
    replacement_records: tuple[BuffRecord, ...]
    result: BuffApplicationResult
    removals: tuple[BuffRemovalResult, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expected_records",
            tuple(sorted(self.expected_records, key=lambda item: item.instance_ref)),
        )
        object.__setattr__(
            self,
            "replacement_records",
            tuple(sorted(self.replacement_records, key=lambda item: item.instance_ref)),
        )
        object.__setattr__(
            self,
            "removals",
            tuple(sorted(self.removals, key=lambda item: item.instance_ref)),
        )


class BuffResolver:
    """根据定义、请求和冲突前值纯计算 Buff 状态变化。"""

    def resolve_apply(
        self,
        definition: BuffDefinition,
        request: ApplyBuffRequest,
        conflicts: tuple[BuffRecord, ...],
        allocated_ref: BuffInstanceRef | None,
    ) -> BuffApplicationResolution:
        _validate_request_matches_definition(definition, request)
        conflicts = tuple(sorted(conflicts, key=lambda item: item.instance_ref))
        if definition.application_policy is BuffApplicationPolicy.COEXIST:
            if allocated_ref is None:
                raise BuffValidationError("coexist 创建分支需要 allocated_ref")
            return self._create(definition, request, allocated_ref, BuffApplicationOutcome.CREATED)
        if definition.application_policy is BuffApplicationPolicy.REPLACE:
            if not conflicts:
                if allocated_ref is None:
                    raise BuffValidationError("replace 创建分支需要 allocated_ref")
                return self._create(
                    definition, request, allocated_ref, BuffApplicationOutcome.CREATED
                )
            if allocated_ref is None:
                raise BuffValidationError("replace 替换分支需要 allocated_ref")
            return self._replace(definition, request, conflicts, allocated_ref)
        if not conflicts:
            if allocated_ref is None:
                raise BuffValidationError("创建分支需要 allocated_ref")
            return self._create(definition, request, allocated_ref, BuffApplicationOutcome.CREATED)
        if allocated_ref is not None:
            raise BuffValidationError("刷新或叠层分支不能分配新 ref")
        existing = _single_compatible_conflict(definition, request, conflicts)
        if definition.application_policy is BuffApplicationPolicy.REFRESH:
            return self._refresh(definition, request, existing)
        if definition.application_policy is BuffApplicationPolicy.STACK_REFRESH:
            return self._stack_refresh(definition, request, existing)
        raise BuffValidationError(f"不支持的 Buff 应用策略：{definition.application_policy.value}")

    def _create(
        self,
        definition: BuffDefinition,
        request: ApplyBuffRequest,
        allocated_ref: BuffInstanceRef,
        outcome: BuffApplicationOutcome,
    ) -> BuffApplicationResolution:
        resolved = _resolved_modifiers(definition, request)
        stack_count = 1
        if definition.application_policy is BuffApplicationPolicy.STACK_REFRESH:
            stack_count = min(request.stack_delta, definition.max_stacks)
        record = BuffRecord(
            instance_ref=allocated_ref,
            definition=definition,
            created_frame=request.frame,
            last_applied_frame=request.frame,
            expires_at_frame=request.frame + request.duration_frames,
            lifecycle_state=BuffLifecycleState.ACTIVE,
            state=BuffState(
                target_ref=request.target_ref,
                applier_ref=request.applier_ref,
                source_context=request.source_context,
                stack_count=stack_count,
                max_stacks=definition.max_stacks,
                resolved_modifiers=resolved,
                tags=definition.tags,
            ),
        )
        result = _application_result(
            definition,
            request,
            outcome=outcome,
            record=record,
            stacks_before=0,
            expires_at_before=None,
            replaced=(),
        )
        return BuffApplicationResolution(
            definition=definition,
            request=request,
            expected_records=(),
            replacement_records=(record,),
            result=result,
        )

    def _replace(
        self,
        definition: BuffDefinition,
        request: ApplyBuffRequest,
        conflicts: tuple[BuffRecord, ...],
        allocated_ref: BuffInstanceRef,
    ) -> BuffApplicationResolution:
        created = self._create(
            definition,
            request,
            allocated_ref,
            BuffApplicationOutcome.REPLACED,
        )
        removed = tuple(
            _removed_record(record, request.frame, BuffRemovalReason.REPLACED)
            for record in conflicts
        )
        removals = tuple(_removal_result(record) for record in removed)
        result = replace(
            created.result,
            replaced_instance_refs=tuple(record.instance_ref for record in conflicts),
        )
        return BuffApplicationResolution(
            definition=definition,
            request=request,
            expected_records=conflicts,
            replacement_records=(*removed, *created.replacement_records),
            result=result,
            removals=removals,
        )

    def _refresh(
        self,
        definition: BuffDefinition,
        request: ApplyBuffRequest,
        existing: BuffRecord,
    ) -> BuffApplicationResolution:
        resolved = _refreshed_modifiers(definition, request, existing)
        refreshed = replace(
            existing,
            last_applied_frame=request.frame,
            expires_at_frame=max(
                existing.expires_at_frame,
                request.frame + request.duration_frames,
            ),
            state=replace(existing.state, resolved_modifiers=resolved),
        )
        result = _application_result(
            definition,
            request,
            outcome=BuffApplicationOutcome.REFRESHED,
            record=refreshed,
            stacks_before=existing.state.stack_count,
            expires_at_before=existing.expires_at_frame,
            replaced=(),
        )
        return BuffApplicationResolution(
            definition=definition,
            request=request,
            expected_records=(existing,),
            replacement_records=(refreshed,),
            result=result,
        )

    def _stack_refresh(
        self,
        definition: BuffDefinition,
        request: ApplyBuffRequest,
        existing: BuffRecord,
    ) -> BuffApplicationResolution:
        stacks_before = existing.state.stack_count
        stacks_after = min(definition.max_stacks, stacks_before + request.stack_delta)
        outcome = (
            BuffApplicationOutcome.STACKED
            if stacks_after > stacks_before
            else BuffApplicationOutcome.STACK_CAPPED_REFRESHED
        )
        resolved = _refreshed_modifiers(definition, request, existing)
        refreshed = replace(
            existing,
            last_applied_frame=request.frame,
            expires_at_frame=max(
                existing.expires_at_frame,
                request.frame + request.duration_frames,
            ),
            state=replace(
                existing.state,
                stack_count=stacks_after,
                resolved_modifiers=resolved,
            ),
        )
        result = _application_result(
            definition,
            request,
            outcome=outcome,
            record=refreshed,
            stacks_before=stacks_before,
            expires_at_before=existing.expires_at_frame,
            replaced=(),
        )
        return BuffApplicationResolution(
            definition=definition,
            request=request,
            expected_records=(existing,),
            replacement_records=(refreshed,),
            result=result,
        )


def _validate_request_matches_definition(
    definition: BuffDefinition,
    request: ApplyBuffRequest,
) -> None:
    if request.definition_key != definition.definition_key:
        raise BuffValidationError(
            f"请求 definition_key {request.definition_key!r} 与定义 "
            f"{definition.definition_key!r} 不一致"
        )
    if request.target_ref.kind not in definition.target_kinds:
        raise BuffValidationError(
            f"Buff {definition.definition_key!r} 不支持目标类型 {request.target_ref.kind.value}"
        )
    if (
        definition.application_policy is not BuffApplicationPolicy.STACK_REFRESH
        and request.stack_delta != 1
    ):
        raise BuffValidationError("非 stack_refresh 策略要求 stack_delta == 1")
    if definition.marker_only:
        if request.modifier_values:
            raise BuffModifierBindingError("marker Buff 请求不能提供 modifier_values")
        return
    values_by_key = {value.term_key: value for value in request.modifier_values}
    expected_keys = tuple(template.term_key for template in definition.attribute_modifiers)
    if tuple(sorted(values_by_key)) != tuple(sorted(expected_keys)):
        raise BuffModifierBindingError(
            f"Buff {definition.definition_key!r} modifier_values 必须完整匹配模板"
        )


def _resolved_modifiers(
    definition: BuffDefinition,
    request: ApplyBuffRequest,
) -> tuple[BuffResolvedAttributeModifier, ...]:
    values_by_key = {value.term_key: value for value in request.modifier_values}
    return tuple(
        BuffResolvedAttributeModifier(template, values_by_key[template.term_key].value)
        for template in definition.attribute_modifiers
    )


def _refreshed_modifiers(
    definition: BuffDefinition,
    request: ApplyBuffRequest,
    existing: BuffRecord,
) -> tuple[BuffResolvedAttributeModifier, ...]:
    if definition.value_refresh_policy is BuffValueRefreshPolicy.KEEP_INITIAL:
        return existing.state.resolved_modifiers
    return _resolved_modifiers(definition, request)


def _single_compatible_conflict(
    definition: BuffDefinition,
    request: ApplyBuffRequest,
    conflicts: tuple[BuffRecord, ...],
) -> BuffRecord:
    if len(conflicts) != 1:
        raise BuffApplicationConflictError(
            f"Buff {definition.definition_key!r} 刷新策略要求唯一兼容冲突记录"
        )
    record = conflicts[0]
    if (
        record.definition.definition_key != request.definition_key
        or record.state.target_ref != request.target_ref
        or record.state.applier_ref != request.applier_ref
        or record.state.source_context != request.source_context
        or not record.is_active_at(request.frame)
    ):
        raise BuffApplicationConflictError(
            f"Buff {definition.definition_key!r} 刷新策略遇到不兼容冲突记录"
        )
    return record


def _application_result(
    definition: BuffDefinition,
    request: ApplyBuffRequest,
    *,
    outcome: BuffApplicationOutcome,
    record: BuffRecord,
    stacks_before: int,
    expires_at_before: int | None,
    replaced: tuple[BuffInstanceRef, ...],
) -> BuffApplicationResult:
    return BuffApplicationResult(
        request_id=request.request_id,
        frame=request.frame,
        order=request.order,
        outcome=outcome,
        instance_ref=record.instance_ref,
        definition_key=definition.definition_key,
        mechanic_key=definition.mechanic_key,
        target_ref=record.state.target_ref,
        applier_ref=record.state.applier_ref,
        source_context=record.state.source_context,
        stacks_before=stacks_before,
        stacks_after=record.state.stack_count,
        expires_at_before=expires_at_before,
        expires_at_after=record.expires_at_frame,
        replaced_instance_refs=replaced,
        resolved_modifiers_after=record.state.resolved_modifiers,
    )


def _removed_record(record: BuffRecord, frame: int, reason: BuffRemovalReason) -> BuffRecord:
    return replace(
        record,
        lifecycle_state=BuffLifecycleState.REMOVED,
        removed_frame=frame,
        removal_reason=reason,
    )


def _removal_result(record: BuffRecord) -> BuffRemovalResult:
    assert record.removed_frame is not None
    assert record.removal_reason is not None
    return BuffRemovalResult(
        frame=record.removed_frame,
        instance_ref=record.instance_ref,
        definition_key=record.definition.definition_key,
        mechanic_key=record.definition.mechanic_key,
        target_ref=record.state.target_ref,
        applier_ref=record.state.applier_ref,
        source_context=record.state.source_context,
        reason=record.removal_reason,
        stack_count=record.state.stack_count,
        scheduled_expires_at_frame=record.expires_at_frame,
    )
