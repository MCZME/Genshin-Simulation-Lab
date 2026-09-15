# 单一关注点：REMOVE_STATUS 影响请求到显式 Buff 移除的契约与链路。
# 覆盖：实例身份两种写法、reason 缺省与非法值、未知字段、请求身份缺失、
# 消费后活动记录消失、分发器路由与忽略分支。
from __future__ import annotations

import pytest

from genshin_sim.core.attributes import AttributeSubjectKind, AttributeSubjectRef
from genshin_sim.core.impacts import ImpactKind, ImpactRequest, ImpactRequestDispatcher
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffImpactContractError,
    BuffRemovalImpactRequestHandler,
    BuffRemovalReason,
)
from tests.helpers.buff import (
    TEST_BUFF_SOURCE,
    build_buff_runtime,
    make_marker_buff_definition,
)

DEFINITION_KEY = "buff.test.consumable"
CONFLICT_KEY = "conflict.test.consumable"
TARGET_REF = AttributeSubjectRef.active_character("player_team")


def _runtime():
    definition = make_marker_buff_definition(
        kind=AttributeSubjectKind.ACTIVE_CHARACTER,
        definition_key=DEFINITION_KEY,
        conflict_key=CONFLICT_KEY,
    )
    return build_buff_runtime(definition)


def _apply(runtime, *, frame: int = 0) -> None:
    runtime.apply(
        ApplyBuffRequest(
            request_id="test:apply:consumable",
            frame=frame,
            order=0,
            definition_key=DEFINITION_KEY,
            target_ref=TARGET_REF,
            source_context=TEST_BUFF_SOURCE,
            duration_frames=600,
            modifier_values=(),
        )
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


def test_removal_impact_consumes_active_buff_by_compact_ref():
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime)
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]

    handler.handle_impact_request(None, _request(instance_ref=record.instance_ref.to_key()))

    assert runtime.reader.active(5, definition_key=DEFINITION_KEY) == ()
    result = handler.records[0].result
    assert result.reason is BuffRemovalReason.CONSUMED
    assert result.instance_ref == record.instance_ref


def test_removal_impact_accepts_instance_ref_object():
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime)
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]

    handler.handle_impact_request(None, _request(instance_ref=record.instance_ref.to_dict()))

    assert runtime.reader.active(5, definition_key=DEFINITION_KEY) == ()


def test_removal_impact_reason_is_explicit_and_defaults_to_consumed():
    runtime = _runtime()
    handler = BuffRemovalImpactRequestHandler(runtime)
    _apply(runtime)
    record = runtime.reader.active(0, definition_key=DEFINITION_KEY)[0]

    handler.handle_impact_request(
        None,
        _request(instance_ref=record.instance_ref.to_key(), reason="dispelled"),
    )

    assert handler.records[0].result.reason is BuffRemovalReason.DISPELLED
    assert handler.records[0].removal_request.frame == 5


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
                extra_fields={"definition_key": DEFINITION_KEY},
            ),
        )


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
