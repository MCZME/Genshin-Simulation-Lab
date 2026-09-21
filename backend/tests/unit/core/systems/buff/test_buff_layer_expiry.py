# 单一关注点：stack_independent 逐层策略——到期、滚动替换、部分提交与输入/构造校验、倍率联动。
from __future__ import annotations

from dataclasses import replace

import pytest

from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeQuery,
    AttributeSubjectKind,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.attributes.resolver import AttributeResolver
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationOutcome,
    BuffApplicationPolicy,
    BuffAttributeModifierProvider,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffModifierValue,
    BuffStackScaling,
    BuffStoreReader,
    BuffSystemError,
    BuffValueRefreshPolicy,
)
from tests.helpers.buff import build_buff_runtime

CHARACTER = AttributeSubjectRef.character("character:slot_1")
SOURCE = RuntimeSourceRef(RuntimeSourceKind.MECHANIC, "mechanic.test_buff", "slot:1")

DURATION_FRAMES = 10
STACK_VALUE = 0.08


def test_stack_independent_definition_allows_multiple_stacks():
    definition = _definition()
    assert definition.max_stacks == 3

    with pytest.raises(BuffSystemError, match="max_stacks"):
        _definition(policy=BuffApplicationPolicy.REFRESH)


@pytest.mark.parametrize(
    ("last_duration", "expected_layers", "expected_expires"),
    [
        pytest.param(DURATION_FRAMES, (12, 14, 16), 16, id="fresh-expiry"),
        pytest.param(4, (10, 12, 14), 14, id="rolling-into-earliest-expiry"),
    ],
)
def test_layers_time_independently_and_rolling_replaces_earliest(
    last_duration: int,
    expected_layers: tuple[int, int, int],
    expected_expires: int,
):
    """各层独立到期；满层滚动始终替换到期最早的一层，层数不变而该层重新计时。

    最后一层的新到期帧既可晚于现存层，也可与最早层相同时保持状态自洽。
    """

    definition = _definition()
    runtime = _runtime(definition)

    first = runtime.apply(_request("layer:1", definition, frame=0))
    second = runtime.apply(_request("layer:2", definition, frame=2))
    third = runtime.apply(_request("layer:3", definition, frame=4))

    assert first.outcome is BuffApplicationOutcome.CREATED
    assert second.outcome is BuffApplicationOutcome.STACKED
    assert third.outcome is BuffApplicationOutcome.STACKED
    record = runtime.buff_store.require(first.instance_ref)
    assert record.state.stack_count == 3
    assert record.state.layer_expires_at_frames == (10, 12, 14)
    assert record.expires_at_frame == 14

    # 满层：替换到期最早的一层。
    fourth = runtime.apply(_request("layer:4", definition, frame=6, duration=last_duration))
    assert fourth.outcome is BuffApplicationOutcome.STACK_ROLLED
    assert (fourth.stacks_before, fourth.stacks_after) == (3, 3)
    rolled = runtime.buff_store.require(first.instance_ref)
    assert rolled.state.stack_count == 3
    assert rolled.state.layer_expires_at_frames == expected_layers
    assert rolled.expires_at_frame == expected_expires
    assert rolled.last_applied_frame == 6


def test_partial_expiry_shrinks_record_and_publishes_no_removal_fact():
    definition = _definition()
    runtime = _runtime(definition)
    first = runtime.apply(_request("layer:1", definition, frame=0))
    runtime.apply(_request("layer:2", definition, frame=2))
    runtime.apply(_request("layer:3", definition, frame=4))
    applied_events = len(runtime.event_engine.frame_events)

    runtime.update_frame(None, 10)
    after_first_layer = runtime.buff_store.require(first.instance_ref)
    assert after_first_layer.state.stack_count == 2
    assert after_first_layer.state.layer_expires_at_frames == (12, 14)
    assert after_first_layer.expires_at_frame == 14
    assert len(runtime.event_engine.frame_events) == applied_events

    runtime.update_frame(None, 12)
    after_second_layer = runtime.buff_store.require(first.instance_ref)
    assert after_second_layer.state.stack_count == 1
    assert after_second_layer.state.layer_expires_at_frames == (14,)
    assert len(runtime.event_engine.frame_events) == applied_events

    runtime.update_frame(None, 14)
    expired = runtime.buff_store.require(first.instance_ref)
    assert expired.state.stack_count == 1
    assert expired.is_active_at(14) is False
    new_events = runtime.event_engine.frame_events[applied_events:]
    assert [event.event_type for event in new_events] == [EventType.BUFF_REMOVED]


def test_store_layer_due_and_whole_due_are_mutually_exclusive():
    definition = _definition()
    runtime = _runtime(definition)
    first = runtime.apply(_request("layer:1", definition, frame=0))
    runtime.apply(_request("layer:2", definition, frame=2))

    assert runtime.buff_store.layers_due_at(9) == ()
    assert runtime.buff_store.layers_due_at(10) == (runtime.buff_store.require(first.instance_ref),)
    assert runtime.buff_store.due_at(10) == ()
    assert runtime.buff_store.layers_due_at(12) == ()
    assert runtime.buff_store.due_at(12) == (runtime.buff_store.require(first.instance_ref),)


def test_stack_delta_above_one_is_rejected():
    definition = _definition()
    runtime = _runtime(definition)

    with pytest.raises(BuffSystemError, match="stack_delta"):
        runtime.apply(_request("layer:bad", definition, stack_delta=2))


def test_linear_stack_scaling_multiplies_by_layer_count():
    definition = _definition(stack_scaling=BuffStackScaling.LINEAR)
    runtime = _runtime(definition)
    runtime.apply(_request("layer:1", definition, frame=0))
    runtime.apply(_request("layer:2", definition, frame=1))
    runtime.apply(_request("layer:3", definition, frame=2))

    provider = BuffAttributeModifierProvider(definition, BuffStoreReader(runtime.buff_store))
    registry = create_public_attribute_registry()
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            ((CHARACTER, BaseAttributeContribution(STAT_ATK_TOTAL, 1000.0, SOURCE)),)
        ),
        modifier_index=ModifierProviderIndex((provider,), registry=registry),
    )

    three_layers = resolver.resolve(AttributeQuery(CHARACTER, STAT_ATK_TOTAL, frame=2))
    assert [term.value for term in three_layers.applied_terms] == [pytest.approx(STACK_VALUE * 3)]

    runtime.update_frame(None, 10)
    two_layers = resolver.resolve(AttributeQuery(CHARACTER, STAT_ATK_TOTAL, frame=11))
    assert [term.value for term in two_layers.applied_terms] == [pytest.approx(STACK_VALUE * 2)]


@pytest.mark.parametrize(
    ("prior_layers", "extra", "expected_layers"),
    [
        pytest.param(
            (("layer:1", 0, 10),),
            ("layer:2", 0, 10),
            (10, 10),
            id="same-frame",
        ),
        pytest.param(
            (("layer:1", 0, 10), ("layer:2", 4, 4)),
            ("layer:3", 5, 5),
            (8, 10, 10),
            id="across-frames",
        ),
    ],
)
def test_matching_expiry_is_accepted(
    prior_layers: tuple[tuple[str, int, int], ...],
    extra: tuple[str, int, int],
    expected_layers: tuple[int, ...],
):
    """新层到期帧与现存层相同时被接受（同帧累积与跨帧重合）。"""

    definition = _definition()
    runtime = _runtime(definition)

    first = runtime.apply(_request("layer:1", definition, frame=0, duration=10))
    for request_id, frame, duration in prior_layers[1:]:
        runtime.apply(_request(request_id, definition, frame=frame, duration=duration))
    last = runtime.apply(_request(extra[0], definition, frame=extra[1], duration=extra[2]))

    assert last.outcome is BuffApplicationOutcome.STACKED
    assert (last.stacks_before, last.stacks_after) == (
        len(expected_layers) - 1,
        len(expected_layers),
    )
    record = runtime.buff_store.require(first.instance_ref)
    assert record.state.stack_count == len(expected_layers)
    assert record.state.layer_expires_at_frames == expected_layers
    assert record.expires_at_frame == max(expected_layers)


def test_layers_sharing_expiry_disappear_together():
    """同一到期帧的多层在部分到期时同时消失，只提交收缩后的记录。"""

    definition = _definition()
    runtime = _runtime(definition)
    first = runtime.apply(_request("layer:1", definition, frame=0, duration=10))
    runtime.apply(_request("layer:2", definition, frame=0, duration=10))
    runtime.apply(_request("layer:3", definition, frame=0, duration=20))
    applied_events = len(runtime.event_engine.frame_events)

    runtime.update_frame(None, 10)

    shrunk = runtime.buff_store.require(first.instance_ref)
    assert shrunk.state.stack_count == 1
    assert shrunk.state.layer_expires_at_frames == (20,)
    assert shrunk.expires_at_frame == 20
    assert len(runtime.event_engine.frame_events) == applied_events


def test_layer_frames_are_rejected_on_non_independent_strategy():
    """非逐层策略携带层帧在记录构造时被拒绝。"""

    definition = _definition()
    runtime = _runtime(definition)
    first = runtime.apply(_request("layer:1", definition, frame=0))
    record = runtime.buff_store.require(first.instance_ref)
    single_stack = _definition(policy=BuffApplicationPolicy.REFRESH, max_stacks=1)

    with pytest.raises(BuffSystemError, match="只有 stack_independent"):
        replace(
            record,
            definition=single_stack,
            state=replace(record.state, max_stacks=1),
        )


def test_independent_strategy_requires_layer_frames():
    """逐层策略缺少层帧在记录构造时被拒绝。"""

    definition = _definition()
    runtime = _runtime(definition)
    first = runtime.apply(_request("layer:1", definition, frame=0))
    record = runtime.buff_store.require(first.instance_ref)

    with pytest.raises(BuffSystemError, match="必须携带逐层到期帧"):
        replace(record, state=replace(record.state, layer_expires_at_frames=()))


def _runtime(*definitions: BuffDefinition):
    return build_buff_runtime(*definitions)


def _definition(
    *,
    policy: BuffApplicationPolicy = BuffApplicationPolicy.STACK_INDEPENDENT,
    stack_scaling: BuffStackScaling = BuffStackScaling.CONSTANT,
    max_stacks: int = 3,
) -> BuffDefinition:
    return BuffDefinition(
        definition_key="buff.layer_expiry",
        mechanic_key="mechanic.test_buff",
        handler_key="test.buff",
        conflict_key="test.buff.layer_expiry",
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=policy,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=max_stacks,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key="atk_bonus",
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                stack_scaling=stack_scaling,
                audit_tags=("test",),
            ),
        ),
        display_name="逐层到期测试",
    )


def _request(
    request_id: str,
    definition: BuffDefinition,
    *,
    frame: int = 0,
    duration: int = DURATION_FRAMES,
    stack_delta: int = 1,
    value: float = STACK_VALUE,
) -> ApplyBuffRequest:
    return ApplyBuffRequest(
        request_id=request_id,
        frame=frame,
        order=0,
        definition_key=definition.definition_key,
        target_ref=CHARACTER,
        source_context=SOURCE,
        duration_frames=duration,
        stack_delta=stack_delta,
        modifier_values=(BuffModifierValue("atk_bonus", value),),
    )
