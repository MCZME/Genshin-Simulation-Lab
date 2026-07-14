from __future__ import annotations

import json

import pytest

from genshin_sim.core.attributes import (
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    AttributeQuery,
    AttributeQueryContext,
    AttributeSubjectKind,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    ModifierProviderSpec,
    ModifierStackingGroupDefinition,
    ModifierStackingPolicy,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
    create_public_attribute_registry,
)
from genshin_sim.core.attributes.resolver import AttributeResolver
from genshin_sim.core.events import EventEngine, EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationOutcome,
    BuffApplicationPolicy,
    BuffAttributeModifierProvider,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffDefinitionRegistry,
    BuffImpactContractError,
    BuffImpactRequestHandler,
    BuffInstanceRef,
    BuffModifierValue,
    BuffPlanConflictError,
    BuffReentrancyError,
    BuffRemovalReason,
    BuffResolver,
    BuffRuntime,
    BuffStackScaling,
    BuffStore,
    BuffStoreReader,
    BuffSystemError,
    BuffValueRefreshPolicy,
    RemoveBuffRequest,
)

CHARACTER = AttributeSubjectRef.character("character:slot_1")
CHARACTER_2 = AttributeSubjectRef.character("character:slot_2")
TARGET = AttributeSubjectRef.target("target:target_1")
SOURCE = RuntimeSourceRef(RuntimeSourceKind.MECHANIC, "mechanic.test_buff", "slot:1")
ASSET_SOURCE = RuntimeSourceRef(RuntimeSourceKind.ASSET, "asset:test")


def test_model_definition_and_instance_validation():
    assert BuffInstanceRef(3).to_key() == "buff:3"

    with pytest.raises(BuffSystemError, match="marker_only"):
        BuffDefinition(
            definition_key="buff.bad_marker",
            mechanic_key="mechanic.bad_marker",
            handler_key="test.buff",
            conflict_key="test.buff.bad_marker",
            target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
            application_policy=BuffApplicationPolicy.REPLACE,
            value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
            max_stacks=1,
            attribute_modifiers=(
                BuffAttributeModifierTemplate(
                    term_key="atk_bonus",
                    target_key=STAT_ATK_TOTAL,
                    stage=ModifierStage.PERCENT_ADD,
                ),
            ),
            marker_only=True,
        )

    with pytest.raises(BuffSystemError, match="max_stacks"):
        _definition(policy=BuffApplicationPolicy.REFRESH, max_stacks=2)

    with pytest.raises(BuffSystemError, match="value"):
        BuffModifierValue("atk_bonus", True)  # type: ignore[arg-type]


def test_replace_refresh_stack_and_coexist_policies_publish_stable_events():
    definition = _definition(policy=BuffApplicationPolicy.REPLACE)
    runtime = _runtime(definition)

    created = runtime.apply(_request("replace:1", definition))
    replaced = runtime.apply(_request("replace:2", definition, frame=1, value=0.2))

    assert created.outcome is BuffApplicationOutcome.CREATED
    assert replaced.outcome is BuffApplicationOutcome.REPLACED
    assert replaced.replaced_instance_refs == (created.instance_ref,)
    assert (
        runtime.buff_store.require(created.instance_ref).removal_reason
        is BuffRemovalReason.REPLACED
    )
    assert [event.event_type for event in runtime.event_engine.frame_events] == [
        EventType.BUFF_APPLIED,
        EventType.BUFF_REMOVED,
        EventType.BUFF_APPLIED,
    ]

    refresh_definition = _definition(
        definition_key="buff.refresh",
        policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.KEEP_INITIAL,
    )
    refresh_runtime = _runtime(refresh_definition)
    first = refresh_runtime.apply(_request("refresh:1", refresh_definition, duration=5, value=0.1))
    second = refresh_runtime.apply(
        _request("refresh:2", refresh_definition, frame=2, duration=1, value=0.8)
    )
    refreshed_record = refresh_runtime.buff_store.require(first.instance_ref)
    assert second.outcome is BuffApplicationOutcome.REFRESHED
    assert second.instance_ref == first.instance_ref
    assert second.expires_at_after == 5
    assert refreshed_record.state.resolved_modifiers[0].value == 0.1

    stack_definition = _definition(
        definition_key="buff.stack",
        policy=BuffApplicationPolicy.STACK_REFRESH,
        max_stacks=3,
    )
    stack_runtime = _runtime(stack_definition)
    stacked_initial = stack_runtime.apply(_request("stack:1", stack_definition, stack_delta=2))
    stacked = stack_runtime.apply(_request("stack:2", stack_definition, frame=1, stack_delta=5))
    capped = stack_runtime.apply(_request("stack:3", stack_definition, frame=2, stack_delta=1))
    assert stacked_initial.stacks_after == 2
    assert stacked.outcome is BuffApplicationOutcome.STACKED
    assert stacked.stacks_after == 3
    assert capped.outcome is BuffApplicationOutcome.STACK_CAPPED_REFRESHED

    coexist_definition = _definition(
        definition_key="buff.coexist",
        policy=BuffApplicationPolicy.COEXIST,
    )
    coexist_runtime = _runtime(coexist_definition)
    one = coexist_runtime.apply(_request("coexist:1", coexist_definition))
    two = coexist_runtime.apply(_request("coexist:2", coexist_definition, frame=1))
    assert one.instance_ref != two.instance_ref
    assert len(coexist_runtime.buff_store.active(1, target_ref=CHARACTER)) == 2


def test_batch_apply_is_atomic_and_request_ids_are_deduplicated():
    definition = _definition()
    runtime = _runtime(definition)
    valid = _request("batch:1", definition, order=0)
    invalid = _request("batch:2", definition, order=1, modifier_values=())

    with pytest.raises(BuffSystemError, match="modifier_values"):
        runtime.apply_many((valid, invalid))
    assert runtime.buff_store.records == ()
    assert runtime.buff_store.version == 0

    runtime.apply(valid)
    with pytest.raises(BuffPlanConflictError, match="已提交"):
        runtime.apply(valid)

    with pytest.raises(BuffSystemError, match="order"):
        runtime.apply_many(
            (
                _request("batch:3", definition, order=0),
                _request("batch:4", definition, order=0),
            )
        )


def test_plan_prevalue_validation_and_explicit_remove():
    definition = _definition()
    runtime = _runtime(definition)
    plan = runtime.prepare_apply((_request("plan:1", definition),))
    runtime.apply(_request("plan:2", definition))

    with pytest.raises(BuffPlanConflictError, match="版本冲突"):
        runtime.validate(plan)

    active_ref = runtime.buff_store.active(0, target_ref=CHARACTER)[0].instance_ref
    removed = runtime.remove(
        RemoveBuffRequest(
            request_id="remove:1",
            frame=0,
            instance_ref=active_ref,
            reason=BuffRemovalReason.EXPLICIT,
        )
    )
    assert removed.reason is BuffRemovalReason.EXPLICIT
    assert runtime.buff_store.require(active_ref).is_active_at(0) is False


def test_validate_rejects_duplicate_operation_after_commit():
    definition = _definition()
    runtime = _runtime(definition)
    plan = runtime.prepare_apply((_request("commit:1", definition),))

    runtime.validate(plan)
    runtime.commit_prevalidated(plan)

    with pytest.raises(BuffPlanConflictError, match="已提交"):
        runtime.validate(plan)


def test_commit_prevalidated_skips_repeat_validation():
    definition = _definition()
    runtime = _runtime(definition)
    plan = runtime.prepare_apply((_request("commit:2", definition),))

    runtime.validate(plan)
    runtime.apply(_request("commit:3", definition, frame=1))
    runtime.commit_prevalidated(plan)

    assert runtime.buff_store.require(BuffInstanceRef(1)).definition.definition_key == (
        definition.definition_key
    )


def test_refresh_rejects_incompatible_source_context():
    definition = _definition(policy=BuffApplicationPolicy.REFRESH)
    runtime = _runtime(definition)
    runtime.apply(_request("conflict:1", definition))

    with pytest.raises(BuffSystemError, match="不兼容冲突记录"):
        runtime.apply(
            _request(
                "conflict:2",
                definition,
                frame=1,
                source_context=RuntimeSourceRef(
                    RuntimeSourceKind.MECHANIC,
                    "mechanic.test_buff",
                    "slot:2",
                ),
            )
        )


def test_lifecycle_boundaries_snapshot_and_event_json_roundtrip():
    definition = _definition()
    runtime = _runtime(definition)
    result = runtime.apply(_request("life:1", definition, frame=100, duration=3))
    assert runtime.buff_store.require(result.instance_ref).is_active_at(100)
    assert runtime.buff_store.require(result.instance_ref).is_active_at(102)
    assert not runtime.buff_store.require(result.instance_ref).is_active_at(103)
    assert len(runtime.snapshot(102).instances) == 1
    applied_payload = json.loads(
        json.dumps(runtime.event_engine.frame_events[-1].payload.to_dict())
    )
    assert applied_payload["result"]["outcome"] == "created"
    assert applied_payload["result"]["expires_at_after"] == 103

    provider = BuffAttributeModifierProvider(definition, BuffStoreReader(runtime.buff_store))
    assert provider.contribute(AttributeQuery(CHARACTER, STAT_ATK_TOTAL, frame=103), object()) == ()
    version_before = runtime.buff_store.version
    runtime.update_frame(None, 103)
    assert runtime.buff_store.version == version_before + 1
    assert (
        runtime.buff_store.require(result.instance_ref).removal_reason is BuffRemovalReason.EXPIRED
    )
    assert runtime.event_engine.frame_events[-1].event_type is EventType.BUFF_REMOVED

    removed_payload = json.loads(
        json.dumps(runtime.event_engine.frame_events[-1].payload.to_dict())
    )
    assert removed_payload["result"]["reason"] == "expired"
    coverage_interval = (
        applied_payload["result"]["frame"],
        min(
            applied_payload["result"]["expires_at_after"],
            removed_payload["result"]["frame"],
        ),
    )
    assert coverage_interval == (100, 103)
    assert json.loads(json.dumps(runtime.snapshot(103).to_dict()))["instances"] == []


def test_runtime_rejects_synchronous_reentry_during_event_publish():
    definition = _definition()
    runtime = _runtime(definition)
    seen: list[str] = []

    def reenter(_event):
        with pytest.raises(BuffReentrancyError):
            runtime.apply(_request("reenter:2", definition, frame=1))
        seen.append("blocked")

    runtime.event_engine.subscribe(EventType.BUFF_APPLIED, reenter)
    runtime.apply(_request("reenter:1", definition))
    assert seen == ["blocked"]


def test_attribute_provider_filters_tags_scales_stacks_and_preserves_audit_source():
    group_key = "test.buff.highest"
    definition = _definition(
        policy=BuffApplicationPolicy.STACK_REFRESH,
        max_stacks=3,
        stack_scaling=BuffStackScaling.LINEAR,
        required_tags=frozenset({"skill"}),
        excluded_tags=frozenset({"burst"}),
        stacking_group=group_key,
    )
    runtime = _runtime(definition)
    runtime.apply(_request("provider:1", definition, stack_delta=2, value=0.1))
    provider = BuffAttributeModifierProvider(definition, BuffStoreReader(runtime.buff_store))

    plain_query = AttributeQuery(CHARACTER, STAT_ATK_TOTAL, frame=0)
    assert provider.contribute(plain_query, object()) == ()
    blocked_query = AttributeQuery(
        CHARACTER,
        STAT_ATK_TOTAL,
        frame=0,
        context=AttributeQueryContext(tags=frozenset({"skill", "burst"})),
    )
    assert provider.contribute(blocked_query, object()) == ()
    isolated_query = AttributeQuery(
        TARGET,
        STAT_ATK_TOTAL,
        frame=0,
        context=AttributeQueryContext(tags=frozenset({"skill"})),
    )
    assert provider.contribute(isolated_query, object()) == ()

    query = AttributeQuery(
        CHARACTER,
        STAT_ATK_TOTAL,
        frame=0,
        context=AttributeQueryContext(tags=frozenset({"skill"})),
    )
    version_before = runtime.buff_store.version
    terms = tuple(provider.contribute(query, object()))
    assert runtime.buff_store.version == version_before
    assert len(terms) == 1
    assert terms[0].value == pytest.approx(0.2)
    assert terms[0].source_ref.kind is RuntimeSourceKind.MECHANIC
    assert terms[0].source_ref.instance_id == "buff:1"
    assert "definition:buff.test" in terms[0].audit_tags
    assert "stacks:2" in terms[0].audit_tags

    registry = create_public_attribute_registry()
    registry.register_stacking_group(
        ModifierStackingGroupDefinition(
            group_key=group_key,
            target_key=STAT_ATK_TOTAL,
            stage=ModifierStage.PERCENT_ADD,
            policy=ModifierStackingPolicy.HIGHEST,
        )
    )
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    CHARACTER,
                    BaseAttributeContribution(STAT_ATK_BASE, 100.0, ASSET_SOURCE),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex((provider,), registry=registry),
    )
    assert resolver.resolve(query).final_value == pytest.approx(120.0)

    competing = StaticModifierProvider(
        ModifierProviderSpec(provider_key="static:highest", writes=frozenset({STAT_ATK_TOTAL})),
        (
            ModifierTerm(
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                value=0.5,
                provider_key="static:highest",
                source_ref=ASSET_SOURCE,
                stacking_group=group_key,
            ),
        ),
        subject_ref=CHARACTER,
    )
    resolver_with_competing = AttributeResolver(
        definitions=registry,
        base_attributes=resolver.base_attributes,
        modifier_index=ModifierProviderIndex((provider, competing), registry=registry),
    )
    resolution = resolver_with_competing.resolve(query)
    assert resolution.final_value == pytest.approx(150.0)
    assert resolution.rejected_terms[0].provider_key == provider.provider_spec.provider_key


def test_apply_status_impact_contract_and_multi_target_atomicity():
    definition = _definition(
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        marker_only=True,
    )
    runtime = _runtime(definition)
    handler = BuffImpactRequestHandler(runtime)
    impact = ImpactRequest(
        frame=5,
        kind=ImpactKind.APPLY_STATUS,
        impact_key="impact.test_buff",
        request_id="impact:1",
        target_refs=("character:slot_1", "character:slot_2"),
        params={
            "buff": {
                "definition_key": definition.definition_key,
                "duration_frames": 4,
                "modifier_values": [],
                "applier_ref": None,
            }
        },
    )
    results = handler.handle_impact_request(_Context(), impact)
    assert [result.target_ref for result in results] == [CHARACTER, CHARACTER_2]
    assert len(runtime.buff_store.active(5)) == 2
    assert results[0].request_id.startswith("buff-impact:8:impact:1")

    bad_impact = ImpactRequest(
        frame=5,
        kind=ImpactKind.APPLY_STATUS,
        impact_key="impact.test_buff",
        request_id="impact:2",
        target_refs=("character:slot_1", "character:slot_1"),
        params={"buff": {"definition_key": definition.definition_key, "duration_frames": 4}},
    )
    with pytest.raises(BuffImpactContractError, match="不能重复"):
        handler.handle_impact_request(_Context(), bad_impact)
    assert len(runtime.buff_store.active(5)) == 2

    extra_field = ImpactRequest(
        frame=5,
        kind=ImpactKind.APPLY_STATUS,
        impact_key="impact.test_buff",
        request_id="impact:3",
        target_refs=("character:slot_1",),
        params={
            "buff": {
                "definition_key": definition.definition_key,
                "duration_frames": 4,
                "unknown": True,
            }
        },
    )
    with pytest.raises(BuffImpactContractError, match="不是受支持字段"):
        handler.handle_impact_request(_Context(), extra_field)
    assert len(runtime.buff_store.active(5)) == 2


def test_apply_status_request_id_distinguishes_multiple_statuses_on_same_impact_point():
    first_definition = _definition(
        definition_key="buff.test.first",
        conflict_key="buff.test.first",
        marker_only=True,
    )
    second_definition = _definition(
        definition_key="buff.test.second",
        conflict_key="buff.test.second",
        marker_only=True,
    )
    runtime = _runtime(first_definition, second_definition)
    handler = BuffImpactRequestHandler(runtime)

    first = handler.handle_impact_request(
        _Context(),
        ImpactRequest(
            frame=5,
            kind=ImpactKind.APPLY_STATUS,
            impact_key="impact.test_buff",
            request_id="impact:shared:1",
            source_impact_point_id="impact-point:shared",
            target_refs=("character:slot_1",),
            params={
                "buff": {
                    "definition_key": first_definition.definition_key,
                    "duration_frames": 4,
                    "modifier_values": [],
                    "applier_ref": None,
                }
            },
        ),
    )[0]
    second = handler.handle_impact_request(
        _Context(),
        ImpactRequest(
            frame=5,
            kind=ImpactKind.APPLY_STATUS,
            impact_key="impact.test_buff",
            request_id="impact:shared:2",
            source_impact_point_id="impact-point:shared",
            target_refs=("character:slot_1",),
            params={
                "buff": {
                    "definition_key": second_definition.definition_key,
                    "duration_frames": 4,
                    "modifier_values": [],
                    "applier_ref": None,
                }
            },
        ),
    )[0]

    assert first.request_id != second.request_id
    assert first.definition_key != second.definition_key
    assert len(runtime.buff_store.active(5, target_ref=CHARACTER)) == 2


def test_apply_status_request_id_uses_length_prefixed_source_impact_point():
    definition = _definition(
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        marker_only=True,
    )
    runtime = _runtime(definition)
    handler = BuffImpactRequestHandler(runtime)
    impact = ImpactRequest(
        frame=2,
        kind=ImpactKind.APPLY_STATUS,
        impact_key="impact.test_buff",
        request_id="fallback-id",
        source_impact_point_id="冲击:一",
        target_refs=("character:槽位一",),
        params={
            "buff": {
                "definition_key": definition.definition_key,
                "duration_frames": 3,
                "modifier_values": [],
            }
        },
    )

    result = handler.handle_impact_request(_Context(), impact)[0]

    assert result.request_id == (
        "buff-impact:4:冲击:一:11:fallback-id:9:buff.test:9:character:13:character:槽位一:0"
    )


class _Context:
    space_runtime = None


def _runtime(*definitions: BuffDefinition) -> BuffRuntime:
    registry = BuffDefinitionRegistry(tuple(definitions))
    store = BuffStore()
    return BuffRuntime(
        definition_registry=registry,
        buff_store=store,
        resolver=BuffResolver(),
        event_engine=EventEngine(),
    )


def _definition(
    *,
    definition_key: str = "buff.test",
    conflict_key: str = "test.buff.conflict",
    policy: BuffApplicationPolicy = BuffApplicationPolicy.REPLACE,
    value_refresh_policy: BuffValueRefreshPolicy = BuffValueRefreshPolicy.REPLACE_LATEST,
    max_stacks: int = 1,
    target_kinds: frozenset[AttributeSubjectKind] | None = None,
    marker_only: bool = False,
    stack_scaling: BuffStackScaling = BuffStackScaling.CONSTANT,
    required_tags: frozenset[str] = frozenset(),
    excluded_tags: frozenset[str] = frozenset(),
    stacking_group: str | None = None,
) -> BuffDefinition:
    modifiers = ()
    if not marker_only:
        modifiers = (
            BuffAttributeModifierTemplate(
                term_key="atk_bonus",
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                stack_scaling=stack_scaling,
                stacking_group=stacking_group,
                required_query_tags=required_tags,
                excluded_query_tags=excluded_tags,
                audit_tags=("test",),
            ),
        )
    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key="mechanic.test_buff",
        handler_key="test.buff",
        conflict_key=conflict_key,
        target_kinds=target_kinds or frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=policy,
        value_refresh_policy=value_refresh_policy,
        max_stacks=max_stacks,
        attribute_modifiers=modifiers,
        marker_only=marker_only,
        tags=frozenset({"test_buff"}),
    )


def _request(
    request_id: str,
    definition: BuffDefinition,
    *,
    frame: int = 0,
    order: int = 0,
    target_ref: AttributeSubjectRef = CHARACTER,
    duration: int = 10,
    stack_delta: int = 1,
    value: float = 0.1,
    modifier_values: tuple[BuffModifierValue, ...] | None = None,
    source_context: RuntimeSourceRef = SOURCE,
) -> ApplyBuffRequest:
    if modifier_values is None:
        modifier_values = () if definition.marker_only else (BuffModifierValue("atk_bonus", value),)
    return ApplyBuffRequest(
        request_id=request_id,
        frame=frame,
        order=order,
        definition_key=definition.definition_key,
        target_ref=target_ref,
        source_context=source_context,
        duration_frames=duration,
        stack_delta=stack_delta,
        modifier_values=modifier_values,
    )
