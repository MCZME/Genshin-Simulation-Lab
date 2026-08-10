"""附魔/转化应用与武器附着收敛的纯解析。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.systems.infusion.definitions import (
    InfusionDefinition,
    validate_non_empty_text,
)
from genshin_sim.core.systems.infusion.enums import (
    EffectiveElementReason,
    InfusionApplicationOutcome,
    InfusionLifecycleState,
    InfusionMode,
    InfusionRemovalReason,
    RefreshPolicy,
)
from genshin_sim.core.systems.infusion.errors import (
    InfusionApplicationConflictError,
    InfusionValidationError,
    UnsupportedWeaponAuraRuleError,
)
from genshin_sim.core.systems.infusion.models import (
    ApplyInfusionRequest,
    EffectiveElementResolution,
    InfusionApplicationResult,
    InfusionInstanceRef,
    InfusionRecord,
    InfusionRemovalResult,
    runtime_source_ref_key,
    validate_frame,
)


@dataclass(frozen=True, slots=True)
class InfusionApplicationResolution:
    definition: InfusionDefinition
    request: ApplyInfusionRequest
    expected_records: tuple[InfusionRecord, ...]
    replacement_records: tuple[InfusionRecord, ...]
    result: InfusionApplicationResult
    removals: tuple[InfusionRemovalResult, ...] = ()

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


class InfusionResolver:
    """根据定义、请求和活动前值纯计算附魔状态变化与最终元素。"""

    def resolve_apply(
        self,
        definition: InfusionDefinition,
        request: ApplyInfusionRequest,
        active_records: tuple[InfusionRecord, ...],
        allocated_ref: InfusionInstanceRef | None,
    ) -> InfusionApplicationResolution:
        _validate_request_matches_definition(definition, request)
        same_target = tuple(
            sorted(
                (
                    record
                    for record in active_records
                    if record.is_active_at(request.frame)
                    and record.character_ref == request.character_ref
                ),
                key=lambda item: item.instance_ref,
            )
        )
        if definition.mode is InfusionMode.CONVERSION:
            conflicts = tuple(
                record for record in same_target if record.mode is InfusionMode.CONVERSION
            )
            if conflicts:
                if allocated_ref is None:
                    raise InfusionValidationError("转化替换分支需要 allocated_ref")
                return self._replace_conversion(definition, request, conflicts, allocated_ref)
            if allocated_ref is None:
                raise InfusionValidationError("创建分支需要 allocated_ref")
            return self._create_conversion(
                definition,
                request,
                allocated_ref,
                InfusionApplicationOutcome.CREATED,
            )

        same_definition = tuple(
            record
            for record in same_target
            if record.mode is InfusionMode.INFUSION
            and record.definition.definition_key == definition.definition_key
        )
        if same_definition:
            if len(same_definition) != 1:
                raise InfusionApplicationConflictError(
                    f"附魔 {definition.definition_key!r} 存在多个同定义活动记录"
                )
            existing = same_definition[0]
            incoming = self._refreshed_record(definition, request, existing)
            outcome = InfusionApplicationOutcome.REFRESHED
            expires_at_before = existing.expires_at_frame
        else:
            if allocated_ref is None:
                raise InfusionValidationError("创建分支需要 allocated_ref")
            incoming = self._created_record(definition, request, allocated_ref)
            outcome = InfusionApplicationOutcome.CREATED
            expires_at_before = None

        converged = converge_application(same_target, incoming)
        result = _application_result(
            definition,
            request,
            outcome=outcome,
            record=incoming,
            expires_at_before=expires_at_before,
            replaced=(),
        )
        return InfusionApplicationResolution(
            definition=definition,
            request=request,
            expected_records=tuple(
                record
                for record in same_target
                if _record_from_refs(converged, record.instance_ref) != record
            ),
            replacement_records=tuple(
                record
                for record in converged
                if _record_from_refs(same_target, record.instance_ref) != record
            ),
            result=result,
        )

    def resolve_effective_element(
        self,
        frame: int,
        character_ref: AttributeSubjectRef,
        base_element: Element,
        active_records: tuple[InfusionRecord, ...],
        attack_tag: str | None = None,
    ) -> EffectiveElementResolution:
        validate_frame(frame)
        if not isinstance(base_element, Element):
            raise InfusionValidationError("base_element 不受支持")
        if attack_tag is not None:
            validate_non_empty_text(attack_tag, "attack_tag")
        records = tuple(
            sorted(
                (
                    record
                    for record in active_records
                    if record.is_active_at(frame)
                    and record.character_ref == character_ref
                    and (
                        attack_tag is None or attack_tag in record.definition.applicable_attack_tags
                    )
                ),
                key=lambda item: item.instance_ref,
            )
        )
        conversions = tuple(record for record in records if record.mode is InfusionMode.CONVERSION)
        if conversions:
            if len(conversions) != 1:
                raise InfusionValidationError("同一角色不能同时存在多个转化来源")
            conversion = conversions[0]
            return EffectiveElementResolution(
                frame=frame,
                character_ref=character_ref,
                element=conversion.element,
                mode=InfusionMode.CONVERSION,
                reason=EffectiveElementReason.CONVERSION,
                source_refs=(conversion.source_context,),
                weapon_gauge=conversion.definition.weapon_gauge,
            )

        infusions = tuple(record for record in records if record.mode is InfusionMode.INFUSION)
        source_refs = tuple(
            sorted(
                (record.source_context for record in infusions),
                key=runtime_source_ref_key,
            )
        )
        if not infusions:
            return EffectiveElementResolution(
                frame=frame,
                character_ref=character_ref,
                element=base_element,
                mode=None,
                reason=EffectiveElementReason.NO_ACTIVE_SOURCE,
                source_refs=(),
                weapon_gauge=None,
            )

        frozen_records = tuple(record for record in infusions if record.frozen)
        if frozen_records:
            carrier = frozen_records[0]
            return EffectiveElementResolution(
                frame=frame,
                character_ref=character_ref,
                element=Element.CRYO,
                mode=InfusionMode.INFUSION,
                reason=EffectiveElementReason.FREEZE,
                source_refs=source_refs,
                weapon_gauge=carrier.definition.weapon_gauge,
            )

        positive = tuple(record for record in infusions if not record.remaining_gauge.is_zero)
        if not positive:
            return EffectiveElementResolution(
                frame=frame,
                character_ref=character_ref,
                element=base_element,
                mode=None,
                reason=EffectiveElementReason.CONSUMED,
                source_refs=source_refs,
                weapon_gauge=None,
            )

        elements = {record.element for record in positive}
        if elements == {Element.HYDRO, Element.ELECTRO}:
            controlling = _controlling_record(
                tuple(record for record in positive if record.element is Element.HYDRO)
            )
            return EffectiveElementResolution(
                frame=frame,
                character_ref=character_ref,
                element=Element.HYDRO,
                mode=InfusionMode.INFUSION,
                reason=EffectiveElementReason.ELECTRO_CHARGED,
                source_refs=source_refs,
                weapon_gauge=controlling.definition.weapon_gauge,
            )
        if len(elements) == 1:
            element = next(iter(elements))
            controlling = _controlling_record(
                tuple(record for record in positive if record.element is element)
            )
            return EffectiveElementResolution(
                frame=frame,
                character_ref=character_ref,
                element=element,
                mode=InfusionMode.INFUSION,
                reason=EffectiveElementReason.SINGLE_SOURCE,
                source_refs=source_refs,
                weapon_gauge=controlling.definition.weapon_gauge,
            )
        raise UnsupportedWeaponAuraRuleError(
            f"不支持的武器附着组合：{sorted(element.value for element in elements)}"
        )

    def _create_conversion(
        self,
        definition: InfusionDefinition,
        request: ApplyInfusionRequest,
        allocated_ref: InfusionInstanceRef,
        outcome: InfusionApplicationOutcome,
    ) -> InfusionApplicationResolution:
        record = self._created_record(definition, request, allocated_ref)
        result = _application_result(
            definition,
            request,
            outcome=outcome,
            record=record,
            expires_at_before=None,
            replaced=(),
        )
        return InfusionApplicationResolution(
            definition=definition,
            request=request,
            expected_records=(),
            replacement_records=(record,),
            result=result,
        )

    def _replace_conversion(
        self,
        definition: InfusionDefinition,
        request: ApplyInfusionRequest,
        conflicts: tuple[InfusionRecord, ...],
        allocated_ref: InfusionInstanceRef,
    ) -> InfusionApplicationResolution:
        created = self._create_conversion(
            definition,
            request,
            allocated_ref,
            InfusionApplicationOutcome.REPLACED,
        )
        removed = tuple(
            _removed_record(record, request.frame, InfusionRemovalReason.REPLACED)
            for record in conflicts
        )
        removals = tuple(_removal_result(record) for record in removed)
        result = replace(
            created.result,
            replaced_instance_refs=tuple(record.instance_ref for record in conflicts),
        )
        return InfusionApplicationResolution(
            definition=definition,
            request=request,
            expected_records=conflicts,
            replacement_records=(*removed, *created.replacement_records),
            result=result,
            removals=removals,
        )

    @staticmethod
    def _created_record(
        definition: InfusionDefinition,
        request: ApplyInfusionRequest,
        allocated_ref: InfusionInstanceRef,
    ) -> InfusionRecord:
        next_refresh_frame = None
        if definition.refresh_policy is RefreshPolicy.PERIODIC:
            assert definition.period_frames is not None
            next_refresh_frame = request.frame + definition.period_frames
        return InfusionRecord(
            instance_ref=allocated_ref,
            definition=definition,
            character_ref=request.character_ref,
            applier_ref=request.applier_ref,
            source_context=request.source_context,
            mode=definition.mode,
            element=definition.element,
            refresh_policy=definition.refresh_policy,
            created_frame=request.frame,
            last_applied_frame=request.frame,
            expires_at_frame=request.frame + definition.duration_frames,
            next_refresh_frame=next_refresh_frame,
            lifecycle_state=InfusionLifecycleState.ACTIVE,
            remaining_gauge=definition.weapon_gauge,
            frozen=False,
        )

    @staticmethod
    def _refreshed_record(
        definition: InfusionDefinition,
        request: ApplyInfusionRequest,
        existing: InfusionRecord,
    ) -> InfusionRecord:
        next_refresh_frame = None
        if definition.refresh_policy is RefreshPolicy.PERIODIC:
            assert definition.period_frames is not None
            next_refresh_frame = request.frame + definition.period_frames
        return replace(
            existing,
            last_applied_frame=request.frame,
            expires_at_frame=max(
                existing.expires_at_frame,
                request.frame + definition.duration_frames,
            ),
            next_refresh_frame=next_refresh_frame,
            remaining_gauge=definition.weapon_gauge,
            frozen=False,
        )


def converge_application(
    active_records: tuple[InfusionRecord, ...],
    incoming: InfusionRecord,
) -> tuple[InfusionRecord, ...]:
    """把一次新的 INFUSION 挂载应用到武器附着集合，返回更新后的完整记录。"""

    frame = incoming.last_applied_frame
    others: list[InfusionRecord] = []
    for record in active_records:
        if record.instance_ref == incoming.instance_ref or not record.is_active_at(frame):
            continue
        if record.frozen:
            record = replace(record, frozen=False, remaining_gauge=AuraAmount.zero())
        others.append(record)

    same_element = tuple(
        record
        for record in others
        if record.mode is InfusionMode.INFUSION
        and record.element == incoming.element
        and not record.remaining_gauge.is_zero
    )
    if same_element:
        others = [
            (
                replace(record, remaining_gauge=AuraAmount.zero())
                if record.element == incoming.element
                else record
            )
            for record in others
        ]
        return tuple(sorted((*others, incoming), key=lambda item: item.instance_ref))

    positive_by_element: dict[Element, InfusionRecord] = {}
    for record in others:
        if record.mode is not InfusionMode.INFUSION or record.remaining_gauge.is_zero:
            continue
        current = positive_by_element.get(record.element)
        if current is None or (record.last_applied_frame, record.instance_ref.sequence) > (
            current.last_applied_frame,
            current.instance_ref.sequence,
        ):
            positive_by_element[record.element] = record

    elements = set(positive_by_element)
    if not elements:
        return tuple(sorted((*others, incoming), key=lambda item: item.instance_ref))
    if len(elements) == 1:
        element = next(iter(elements))
        existing = positive_by_element[element]
        incoming, existing = _consume_pair(incoming, existing)
        return tuple(
            sorted(
                (
                    replace(
                        record,
                        remaining_gauge=(
                            existing.remaining_gauge
                            if record.instance_ref == existing.instance_ref
                            else record.remaining_gauge
                        ),
                    )
                    if record.instance_ref == existing.instance_ref
                    else record
                    for record in (*others, incoming)
                ),
                key=lambda item: item.instance_ref,
            )
        )
    if elements == {Element.HYDRO, Element.ELECTRO}:
        electro = positive_by_element[Element.ELECTRO]
        hydro = positive_by_element[Element.HYDRO]
        if incoming.element in {Element.PYRO, Element.CRYO}:
            incoming, electro = _consume_pair(incoming, electro)
            if not incoming.remaining_gauge.is_zero:
                incoming, hydro = _consume_pair(incoming, hydro)
            updated = {
                electro.instance_ref: electro,
                hydro.instance_ref: hydro,
            }
        elif incoming.element is Element.HYDRO:
            updated = {
                electro.instance_ref: electro,
                hydro.instance_ref: replace(
                    hydro,
                    remaining_gauge=AuraAmount.zero(),
                ),
            }
        elif incoming.element is Element.ELECTRO:
            updated = {
                electro.instance_ref: replace(
                    electro,
                    remaining_gauge=AuraAmount.zero(),
                ),
                hydro.instance_ref: hydro,
            }
        else:
            raise UnsupportedWeaponAuraRuleError(f"不支持的雷水共存挂载：{incoming.element.value}")
        return tuple(
            sorted(
                (updated.get(record.instance_ref, record) for record in (*others, incoming)),
                key=lambda item: item.instance_ref,
            )
        )
    raise UnsupportedWeaponAuraRuleError(
        f"不支持的武器附着组合：{sorted(element.value for element in elements)}"
    )


def _consume_pair(
    incoming: InfusionRecord,
    existing: InfusionRecord,
) -> tuple[InfusionRecord, InfusionRecord]:
    """按已冻结六对规则处理一次后手挂载与先手残留的消耗。"""

    incoming_amount = incoming.remaining_gauge
    existing_amount = existing.remaining_gauge
    incoming_element = incoming.element
    existing_element = existing.element

    if incoming_element is Element.PYRO and existing_element is Element.CRYO:
        consumed = incoming_amount.minimum(existing_amount / 2)
        return (
            replace(incoming, remaining_gauge=incoming_amount - consumed),
            replace(existing, remaining_gauge=existing_amount - consumed * 2),
        )
    if incoming_element is Element.CRYO and existing_element is Element.PYRO:
        consumed = incoming_amount.minimum(existing_amount * 2)
        return (
            replace(incoming, remaining_gauge=incoming_amount - consumed),
            replace(existing, remaining_gauge=existing_amount - consumed / 2),
        )
    if incoming_element is Element.HYDRO and existing_element is Element.PYRO:
        consumed = incoming_amount.minimum(existing_amount / 2)
        return (
            replace(incoming, remaining_gauge=incoming_amount - consumed),
            replace(existing, remaining_gauge=existing_amount - consumed * 2),
        )
    if incoming_element is Element.PYRO and existing_element is Element.HYDRO:
        consumed = incoming_amount.minimum(existing_amount * 2)
        return (
            replace(incoming, remaining_gauge=incoming_amount - consumed),
            replace(existing, remaining_gauge=existing_amount - consumed / 2),
        )
    if incoming_element is Element.ELECTRO and existing_element is Element.CRYO:
        consumed = incoming_amount.minimum(existing_amount)
        return (
            replace(incoming, remaining_gauge=incoming_amount - consumed),
            replace(existing, remaining_gauge=existing_amount - consumed),
        )
    if incoming_element is Element.CRYO and existing_element is Element.ELECTRO:
        consumed = incoming_amount.minimum(existing_amount)
        return (
            replace(incoming, remaining_gauge=incoming_amount - consumed),
            replace(existing, remaining_gauge=existing_amount - consumed),
        )
    if incoming_element is Element.ELECTRO and existing_element is Element.PYRO:
        consumed = incoming_amount.minimum(existing_amount)
        return (
            replace(incoming, remaining_gauge=incoming_amount - consumed),
            replace(existing, remaining_gauge=existing_amount - consumed),
        )
    if incoming_element is Element.PYRO and existing_element is Element.ELECTRO:
        consumed = incoming_amount.minimum(existing_amount)
        return (
            replace(incoming, remaining_gauge=incoming_amount - consumed),
            replace(existing, remaining_gauge=existing_amount - consumed),
        )
    if {incoming_element, existing_element} == {Element.HYDRO, Element.CRYO}:
        reaction = incoming_amount.minimum(existing_amount)
        return (
            replace(
                incoming,
                remaining_gauge=incoming_amount - reaction,
                frozen=True,
            ),
            replace(existing, remaining_gauge=existing_amount - reaction),
        )
    if {incoming_element, existing_element} == {Element.HYDRO, Element.ELECTRO}:
        return (
            replace(
                incoming,
                remaining_gauge=incoming_amount * AuraAmount("4/5"),
            ),
            existing,
        )
    raise UnsupportedWeaponAuraRuleError(
        f"不支持的武器消耗组合：{incoming_element.value} -> {existing_element.value}"
    )


def _controlling_record(records: tuple[InfusionRecord, ...]) -> InfusionRecord:
    return max(records, key=lambda item: (item.last_applied_frame, item.instance_ref.sequence))


def _validate_request_matches_definition(
    definition: InfusionDefinition,
    request: ApplyInfusionRequest,
) -> None:
    if request.definition_key != definition.definition_key:
        raise InfusionValidationError(
            f"请求 definition_key {request.definition_key!r} 与定义 "
            f"{definition.definition_key!r} 不一致"
        )
    if request.character_ref.kind not in definition.target_kinds:
        raise InfusionValidationError(
            f"附魔定义 {definition.definition_key!r} 不支持目标类型 "
            f"{request.character_ref.kind.value}"
        )


def _application_result(
    definition: InfusionDefinition,
    request: ApplyInfusionRequest,
    *,
    outcome: InfusionApplicationOutcome,
    record: InfusionRecord,
    expires_at_before: int | None,
    replaced: tuple[InfusionInstanceRef, ...],
) -> InfusionApplicationResult:
    return InfusionApplicationResult(
        request_id=request.request_id,
        frame=request.frame,
        order=request.order,
        outcome=outcome,
        instance_ref=record.instance_ref,
        definition_key=definition.definition_key,
        mechanic_key=definition.mechanic_key,
        mode=record.mode,
        element=record.element,
        character_ref=record.character_ref,
        applier_ref=record.applier_ref,
        source_context=record.source_context,
        expires_at_before=expires_at_before,
        expires_at_after=record.expires_at_frame,
        next_refresh_frame_after=record.next_refresh_frame,
        replaced_instance_refs=replaced,
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


def _removal_result(record: InfusionRecord) -> InfusionRemovalResult:
    assert record.removed_frame is not None
    assert record.removal_reason is not None
    return InfusionRemovalResult(
        frame=record.removed_frame,
        instance_ref=record.instance_ref,
        definition_key=record.definition.definition_key,
        mechanic_key=record.definition.mechanic_key,
        mode=record.mode,
        element=record.element,
        character_ref=record.character_ref,
        reason=record.removal_reason,
        scheduled_expires_at_frame=record.expires_at_frame,
    )


def _record_from_refs(
    records: tuple[InfusionRecord, ...],
    instance_ref: InfusionInstanceRef,
) -> InfusionRecord | None:
    return next((record for record in records if record.instance_ref == instance_ref), None)
