# 单一关注点：REMOVE_STATUS 影响请求到显式 Buff 移除/减层的契约与链路。
# 覆盖：实例身份两种写法、reason 缺省与非法值、未知字段、请求身份缺失、
# 消费后活动记录消失、definition_key 形态（整条移除/按层数减少/未持层跳过/
# 双形态互斥）、分发器路由与忽略分支。
from __future__ import annotations

from types import SimpleNamespace

import pytest

from genshin_sim.core.attributes import AttributeSubjectKind, AttributeSubjectRef
from genshin_sim.core.impacts import ImpactKind, ImpactRequest, ImpactRequestDispatcher
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffDefinition,
    BuffImpactContractError,
    BuffRemovalImpactRequestHandler,
    BuffRemovalReason,
    BuffRemovalResult,
    BuffStackReductionResult,
)
from genshin_sim.core.systems.buff.enums import (
    BuffApplicationPolicy,
    BuffValueRefreshPolicy,
)
from tests.helpers.buff import (
    TEST_BUFF_HANDLER_KEY,
    TEST_BUFF_MECHANIC_KEY,
    TEST_BUFF_SOURCE,
    build_buff_runtime,
    make_marker_buff_definition,
)

DEFINITION_KEY = "buff.test.consumable"
CONFLICT_KEY = "conflict.test.consumable"
TARGET_REF = AttributeSubjectRef.active_character("player_team")


def _null_context() -> SimpleNamespace:
    """definition_key 形态不读取 space_runtime，用无副作用上下文占位。"""

    return SimpleNamespace(space_runtime=None)


def _removal_result(
    result: BuffRemovalResult | BuffStackReductionResult,
) -> BuffRemovalResult:
    """收窄为整条移除结果：REMOVE_STATUS 的两种形态共用同一返回联合类型。"""

    assert isinstance(result, BuffRemovalResult)
    return result


def _reduction_result(
    result: BuffRemovalResult | BuffStackReductionResult,
) -> BuffStackReductionResult:
    """收窄为减层结果。"""

    assert isinstance(result, BuffStackReductionResult)
    return result


def _runtime():
    definition = make_marker_buff_definition(
        kind=AttributeSubjectKind.ACTIVE_CHARACTER,
        definition_key=DEFINITION_KEY,
        conflict_key=CONFLICT_KEY,
    )
    return build_buff_runtime(definition)


def _stackable_runtime(*, max_stacks: int = 5):
    definition = BuffDefinition(
        definition_key=DEFINITION_KEY,
        mechanic_key=TEST_BUFF_MECHANIC_KEY,
        handler_key=TEST_BUFF_HANDLER_KEY,
        conflict_key=CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.STACK_REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=max_stacks,
        marker_only=True,
    )
    return build_buff_runtime(definition)


_CHARACTER_REF = AttributeSubjectRef.character("character:slot_1")


def _apply(runtime, *, frame: int = 0, stack_delta: int = 1, target_ref=TARGET_REF) -> None:
    runtime.apply(
        ApplyBuffRequest(
            request_id="test:apply:consumable",
            frame=frame,
            order=0,
            definition_key=DEFINITION_KEY,
            target_ref=target_ref,
            source_context=TEST_BUFF_SOURCE,
            duration_frames=600,
            stack_delta=stack_delta,
            modifier_values=(),
        )
    )


def _definition_keyed_request(
    *,
    stacks: int | None,
    extra_targets: tuple[AttributeSubjectRef, ...] = (),
) -> ImpactRequest:
    payload: dict[str, object] = {"definition_key": DEFINITION_KEY}
    if stacks is not None:
        payload["stacks"] = stacks
    return ImpactRequest(
        frame=5,
        kind=ImpactKind.REMOVE_STATUS,
        impact_key="test.consume_buff",
        owner_slot=1,
        request_id="impact:test:remove",
        target_refs=("character:slot_1", *(ref.entity_id for ref in extra_targets)),
        params={"buff_remove": payload},
    )


def _request(
    *,
    instance_ref: object,
    reason: object | None = None,
    frame: int = 5,
    request_id: str | None = "impact:test:remove",
    source_impact_point_id: str | None = None,
    extra_fields: dict[str, object] | None = None,
) -> ImpactRequest:
    payload: dict[str, object] = {"instance_ref": instance_ref}
    if reason is not None:
        payload["reason"] = reason
    if extra_fields:
        payload.update(extra_fields)
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.REMOVE_STATUS,
        impact_key="test.consume_buff",
        owner_slot=1,
        request_id=request_id,
        source_impact_point_id=source_impact_point_id,
        params={"buff_remove": payload},
    )


@pytest.mark.parametrize(
    ("as_dict",),
    ((False,), (True,)),
    ids=("compact_ref", "instance_ref_object"),
)
def test_removal_impact_consumes_active_buff(as_dict: bool) -> None:
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime)
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]
    instance_ref = record.instance_ref.to_dict() if as_dict else record.instance_ref.to_key()

    handler.handle_impact_request(None, _request(instance_ref=instance_ref))

    assert runtime.reader.active(5, definition_key=DEFINITION_KEY) == ()
    result = _removal_result(handler.records[0].results[0])
    assert result.reason is BuffRemovalReason.CONSUMED
    assert result.instance_ref == record.instance_ref


def test_removal_impact_reason_is_explicit_and_defaults_to_consumed():
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime)
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]

    handler.handle_impact_request(
        None,
        _request(instance_ref=record.instance_ref.to_key(), reason="dispelled"),
    )

    removal_request = handler.records[0].removal_request
    assert removal_request is not None
    assert _removal_result(handler.records[0].results[0]).reason is BuffRemovalReason.DISPELLED
    assert removal_request.frame == 5


def test_removal_impact_rejects_unknown_field():
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime)
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]

    with pytest.raises(BuffImpactContractError, match="不是受支持字段"):
        handler.handle_impact_request(
            None,
            _request(
                instance_ref=record.instance_ref.to_key(),
                extra_fields={"unexpected": 1},
            ),
        )


def test_removal_impact_rejects_dual_identity():
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime)
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]

    with pytest.raises(BuffImpactContractError, match="只能提供 instance_ref 或 definition_key"):
        handler.handle_impact_request(
            None,
            _request(
                instance_ref=record.instance_ref.to_key(),
                extra_fields={"definition_key": DEFINITION_KEY},
            ),
        )


def test_definition_keyed_removal_clears_target_record():
    runtime = _stackable_runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime, stack_delta=3, target_ref=_CHARACTER_REF)

    results = handler.handle_impact_request(
        _null_context(),
        _definition_keyed_request(stacks=None),
    )

    assert runtime.reader.active(5, definition_key=DEFINITION_KEY) == ()
    assert len(results) == 1
    assert _removal_result(results[0]).reason is BuffRemovalReason.CONSUMED


def test_definition_keyed_reduction_removes_partial_stacks():
    runtime = _stackable_runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime, stack_delta=3, target_ref=_CHARACTER_REF)

    results = handler.handle_impact_request(
        _null_context(),
        _definition_keyed_request(stacks=2),
    )

    record = runtime.reader.active(5, definition_key=DEFINITION_KEY)[0]
    assert record.state.stack_count == 1
    assert len(results) == 1
    reduction = _reduction_result(results[0])
    assert reduction.stacks_before == 3
    assert reduction.stacks_after == 1
    assert reduction.removed is False


def test_definition_keyed_reduction_to_zero_removes_record():
    runtime = _stackable_runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime, stack_delta=2, target_ref=_CHARACTER_REF)

    results = handler.handle_impact_request(
        _null_context(),
        _definition_keyed_request(stacks=5),
    )

    assert runtime.reader.active(5, definition_key=DEFINITION_KEY) == ()
    assert len(results) == 1
    reduction = _reduction_result(results[0])
    assert reduction.removed is True
    removal_result = reduction.removal_result
    assert removal_result is not None
    assert removal_result.reason is BuffRemovalReason.CONSUMED


def test_definition_keyed_removal_skips_targets_without_buff():
    runtime = _stackable_runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime, stack_delta=1, target_ref=_CHARACTER_REF)
    other_ref = AttributeSubjectRef.character("character:slot_2")

    results = handler.handle_impact_request(
        _null_context(),
        _definition_keyed_request(stacks=None, extra_targets=(other_ref,)),
    )

    assert len(results) == 1
    assert _removal_result(results[0]).target_ref == _CHARACTER_REF
    assert runtime.reader.active(5, definition_key=DEFINITION_KEY) == ()


def test_removal_impact_rejects_unsupported_reason():
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime)
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]

    with pytest.raises(BuffImpactContractError, match="reason 不受支持"):
        handler.handle_impact_request(
            None,
            _request(instance_ref=record.instance_ref.to_key(), reason="expired"),
        )


def test_removal_impact_requires_request_identity():
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime)
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]

    with pytest.raises(BuffImpactContractError, match="必须提供 source_impact_point_id"):
        handler.handle_impact_request(
            None,
            _request(instance_ref=record.instance_ref.to_key(), request_id=None),
        )


def test_removal_impact_ignores_only_bound_instance():
    """消费只作用于给定实例：同主体上的其他 Definition 不受影响。"""

    other = make_marker_buff_definition(
        kind=AttributeSubjectKind.ACTIVE_CHARACTER,
        definition_key="buff.test.other",
        conflict_key="conflict.test.other",
    )
    runtime = build_buff_runtime(
        make_marker_buff_definition(
            kind=AttributeSubjectKind.ACTIVE_CHARACTER,
            definition_key=DEFINITION_KEY,
            conflict_key=CONFLICT_KEY,
        ),
        other,
    )
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime)
    runtime.apply(
        ApplyBuffRequest(
            request_id="test:apply:other",
            frame=0,
            order=1,
            definition_key=other.definition_key,
            target_ref=TARGET_REF,
            source_context=TEST_BUFF_SOURCE,
            duration_frames=600,
            modifier_values=(),
        )
    )
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]

    handler.handle_impact_request(None, _request(instance_ref=record.instance_ref.to_key()))

    assert runtime.reader.active(5, definition_key=DEFINITION_KEY) == ()
    assert len(runtime.reader.active(5, definition_key=other.definition_key)) == 1


def test_dispatcher_routes_remove_status_to_removal_handler():
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    dispatcher = ImpactRequestDispatcher(buff_removal_handler=handler)
    _apply(runtime)
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]

    dispatcher.dispatch_requests(None, (_request(instance_ref=record.instance_ref.to_key()),))

    assert dispatcher.buff_removal_records == handler.records
    assert dispatcher.ignored_requests == ()


def test_dispatcher_ignores_remove_status_without_contract():
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    dispatcher = ImpactRequestDispatcher(buff_removal_handler=handler)
    request = ImpactRequest(
        frame=1,
        kind=ImpactKind.REMOVE_STATUS,
        impact_key="test.consume_buff",
        params={},
    )

    dispatcher.dispatch_requests(None, (request,))

    assert len(dispatcher.ignored_requests) == 1
    assert "buff_remove" in dispatcher.ignored_requests[0].reason


def test_dispatcher_ignores_remove_status_when_handler_missing():
    dispatcher = ImpactRequestDispatcher()
    request = ImpactRequest(
        frame=1,
        kind=ImpactKind.REMOVE_STATUS,
        impact_key="test.consume_buff",
        params={"buff_remove": {"instance_ref": "buff:1"}},
    )

    dispatcher.dispatch_requests(None, (request,))

    assert dispatcher.buff_removal_records == ()
    assert len(dispatcher.ignored_requests) == 1
    assert "尚未接入" in dispatcher.ignored_requests[0].reason
