from __future__ import annotations

import json

import pytest

from genshin_sim.core.attributes import AttributeSubjectKind, AttributeSubjectRef
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.systems.infusion import (
    EffectiveElementReason,
    EffectiveElementResolution,
    InfusionApplicationOutcome,
    InfusionApplicationResult,
    InfusionDefinition,
    InfusionDefinitionConflictError,
    InfusionDefinitionNotFoundError,
    InfusionDefinitionRegistry,
    InfusionInstanceRef,
    InfusionLifecycleState,
    InfusionMode,
    InfusionMutationPlan,
    InfusionRemovalReason,
    InfusionSystemError,
    RefreshPolicy,
)
from genshin_sim.core.systems.infusion.models import RemoveInfusionRequest
from tests.helpers.infusion import (
    CHARACTER,
    SOURCE,
    SOURCE_2,
    make_definition,
    make_record,
    make_request,
)


def test_infusion_definition_validates_fields_and_serializes():
    definition = make_definition(weapon_gauge=AuraAmount(2))
    assert definition.mode is InfusionMode.INFUSION
    assert definition.element is Element.PYRO
    assert definition.weapon_gauge == AuraAmount(2)
    assert definition.target_kinds == frozenset({AttributeSubjectKind.CHARACTER})
    payload = json.loads(json.dumps(definition.to_dict()))
    assert payload["weapon_gauge"]["numerator"] == 2
    assert payload["mode"] == "infusion"

    with pytest.raises(InfusionSystemError, match="物理"):
        make_definition(element=Element.PHYSICAL)
    with pytest.raises(InfusionSystemError, match="weapon_gauge"):
        make_definition(weapon_gauge=AuraAmount.zero())
    with pytest.raises(InfusionSystemError, match="applicable_attack_tags"):
        make_definition(applicable_attack_tags=frozenset())
    with pytest.raises(InfusionSystemError, match="period_frames"):
        make_definition(refresh_policy=RefreshPolicy.PERIODIC)
    with pytest.raises(InfusionSystemError, match="period_frames <= duration_frames"):
        make_definition(
            refresh_policy=RefreshPolicy.PERIODIC,
            period_frames=6,
            duration_frames=4,
        )
    periodic_ok = make_definition(
        refresh_policy=RefreshPolicy.PERIODIC,
        period_frames=4,
        duration_frames=4,
    )
    assert periodic_ok.period_frames == 4
    with pytest.raises(InfusionSystemError, match="ONCE"):
        make_definition(period_frames=5)
    with pytest.raises(InfusionSystemError, match="角色主体"):
        make_definition(target_kinds=frozenset({AttributeSubjectKind.TARGET}))


def test_infusion_definition_registry_rejects_duplicates():
    first = make_definition()
    second = make_definition(definition_key="infusion.test.other")
    registry = InfusionDefinitionRegistry((first, second))
    assert registry.get(first.definition_key) is first
    assert registry.contains(second.definition_key)
    with pytest.raises(InfusionDefinitionConflictError, match="重复"):
        registry.register(first)
    with pytest.raises(InfusionDefinitionNotFoundError, match="未知"):
        InfusionDefinitionRegistry().get("missing")


def test_infusion_instance_ref_and_requests_validate():
    assert InfusionInstanceRef(3).to_key() == "infusion:3"
    assert str(InfusionInstanceRef(3)) == "infusion:3"
    with pytest.raises(InfusionSystemError, match="正整数"):
        InfusionInstanceRef(0)
    with pytest.raises(InfusionSystemError, match="domain_key"):
        InfusionInstanceRef(1, domain_key="buff")

    definition = make_definition()
    request = make_request("req:1", definition)
    assert request.character_ref == CHARACTER
    with pytest.raises(InfusionSystemError, match="角色主体"):
        make_request(
            "req:2",
            definition,
            character_ref=AttributeSubjectRef.target("target:target_1"),
        )
    with pytest.raises(InfusionSystemError, match="只允许 dispelled"):
        RemoveInfusionRequest(
            request_id="remove:1",
            frame=0,
            instance_ref=InfusionInstanceRef(1),
            reason=InfusionRemovalReason.EXPIRED,
        )


def test_infusion_record_lifecycle_invariants():
    definition = make_definition(duration_frames=5)
    record = make_record(InfusionInstanceRef(1), definition, expires_at_frame=5)
    assert record.is_active_at(0)
    assert record.is_active_at(4)
    assert not record.is_active_at(5)
    assert json.loads(json.dumps(record.to_dict()))["lifecycle_state"] == "active"

    with pytest.raises(InfusionSystemError, match="last_applied"):
        make_record(InfusionInstanceRef(2), definition, last_applied_frame=3, expires_at_frame=2)
    with pytest.raises(InfusionSystemError, match="next_refresh_frame"):
        make_record(InfusionInstanceRef(3), definition, next_refresh_frame=4)

    periodic = make_definition(refresh_policy=RefreshPolicy.PERIODIC, period_frames=5)
    periodic_record = make_record(
        InfusionInstanceRef(4),
        periodic,
        next_refresh_frame=5,
    )
    assert periodic_record.is_active_at(0)
    with pytest.raises(InfusionSystemError, match="next_refresh_frame"):
        make_record(InfusionInstanceRef(5), periodic)

    expired = make_record(
        InfusionInstanceRef(6),
        definition,
        lifecycle_state=InfusionLifecycleState.EXPIRED,
        removed_frame=3,
        removal_reason=InfusionRemovalReason.EXPIRED,
    )
    assert expired.lifecycle_state is InfusionLifecycleState.EXPIRED
    with pytest.raises(InfusionSystemError, match="不能对应 expired"):
        make_record(
            InfusionInstanceRef(7),
            definition,
            lifecycle_state=InfusionLifecycleState.REMOVED,
            removed_frame=3,
            removal_reason=InfusionRemovalReason.EXPIRED,
        )
    with pytest.raises(InfusionSystemError, match="expired"):
        make_record(
            InfusionInstanceRef(8),
            definition,
            lifecycle_state=InfusionLifecycleState.EXPIRED,
            removed_frame=3,
            removal_reason=InfusionRemovalReason.REPLACED,
        )
    with pytest.raises(InfusionSystemError, match="活动记录"):
        make_record(
            InfusionInstanceRef(9),
            definition,
            removed_frame=3,
            removal_reason=InfusionRemovalReason.EXPLICIT,
        )


def test_effective_element_resolution_validates_and_serializes():
    resolution = EffectiveElementResolution(
        frame=5,
        character_ref=CHARACTER,
        element=Element.CRYO,
        mode=InfusionMode.INFUSION,
        reason=EffectiveElementReason.SINGLE_SOURCE,
        source_refs=(SOURCE_2, SOURCE),
    )
    assert resolution.source_refs == (SOURCE, SOURCE_2)
    payload = json.loads(json.dumps(resolution.to_dict()))
    assert payload["element"] == "cryo"
    assert payload["reason"] == "single_source"

    with pytest.raises(InfusionSystemError, match="转化"):
        EffectiveElementResolution(
            frame=5,
            character_ref=CHARACTER,
            element=Element.CRYO,
            mode=InfusionMode.CONVERSION,
            reason=EffectiveElementReason.CONVERSION,
            source_refs=(SOURCE, SOURCE_2),
        )
    with pytest.raises(InfusionSystemError, match="重复"):
        EffectiveElementResolution(
            frame=5,
            character_ref=CHARACTER,
            element=Element.CRYO,
            mode=InfusionMode.INFUSION,
            reason=EffectiveElementReason.SINGLE_SOURCE,
            source_refs=(SOURCE, SOURCE),
        )
    with pytest.raises(InfusionSystemError, match="RuntimeSourceRef"):
        EffectiveElementResolution(
            frame=5,
            character_ref=CHARACTER,
            element=Element.CRYO,
            mode=InfusionMode.INFUSION,
            reason=EffectiveElementReason.SINGLE_SOURCE,
            source_refs=("not-a-source-ref",),  # type: ignore[arg-type]
        )


def test_infusion_mutation_plan_sorts_and_rejects_duplicates():
    definition = make_definition()
    result_a = _result("a", definition, order=1, sequence=2)
    result_b = _result("b", definition, order=0, sequence=1)
    plan = InfusionMutationPlan(
        operation_id="plan:1",
        frame=0,
        expected_store_version=0,
        request_ids=("a", "b"),
        application_results=(result_a, result_b),
    )
    assert [result.order for result in plan.application_results] == [0, 1]
    assert [result.instance_ref.sequence for result in plan.application_results] == [1, 2]

    with pytest.raises(InfusionSystemError, match="request_ids"):
        InfusionMutationPlan(
            operation_id="plan:2",
            frame=0,
            expected_store_version=0,
            request_ids=("a", "a"),
        )


def _result(
    request_id: str,
    definition: InfusionDefinition,
    *,
    order: int,
    sequence: int,
) -> InfusionApplicationResult:
    return InfusionApplicationResult(
        request_id=request_id,
        frame=0,
        order=order,
        outcome=InfusionApplicationOutcome.CREATED,
        instance_ref=InfusionInstanceRef(sequence),
        definition_key=definition.definition_key,
        mechanic_key=definition.mechanic_key,
        mode=definition.mode,
        element=definition.element,
        character_ref=CHARACTER,
        applier_ref=None,
        source_context=SOURCE,
        expires_at_before=None,
        expires_at_after=10,
        next_refresh_frame_after=None,
    )
