# 单一关注点：Buff 载荷词条（payload_terms）——不进属性系统的机制数值证据。
from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
)
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffModifierBindingError,
    BuffModifierValue,
    BuffPayloadTermTemplate,
    BuffValidationError,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.buff.snapshots import BuffSnapshot
from tests.helpers.buff import TEST_BUFF_MECHANIC_KEY, TEST_BUFF_SOURCE, build_buff_runtime

CHARACTER = AttributeSubjectRef.character("character:slot_1")


def _payload_only_definition(
    *,
    value_refresh_policy: BuffValueRefreshPolicy = BuffValueRefreshPolicy.REPLACE_LATEST,
) -> BuffDefinition:
    return BuffDefinition(
        definition_key="buff.test.payload_only",
        mechanic_key=TEST_BUFF_MECHANIC_KEY,
        handler_key="test.buff",
        conflict_key="test.buff.payload_only",
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=value_refresh_policy,
        max_stacks=1,
        payload_terms=(BuffPayloadTermTemplate(term_key="test.payload.evidence"),),
        display_name="载荷词条测试",
    )


def _mixed_definition() -> BuffDefinition:
    return BuffDefinition(
        definition_key="buff.test.mixed",
        mechanic_key=TEST_BUFF_MECHANIC_KEY,
        handler_key="test.buff",
        conflict_key="test.buff.mixed",
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key="test.mixed.atk",
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        payload_terms=(BuffPayloadTermTemplate(term_key="test.mixed.evidence"),),
    )


def _apply_request(
    definition: BuffDefinition,
    values: tuple[BuffModifierValue, ...],
    frame: int = 10,
) -> ApplyBuffRequest:
    return ApplyBuffRequest(
        request_id=f"req:{definition.definition_key}:{frame}",
        frame=frame,
        order=0,
        definition_key=definition.definition_key,
        target_ref=CHARACTER,
        source_context=TEST_BUFF_SOURCE,
        duration_frames=100,
        modifier_values=values,
    )


def test_payload_only_definition_applies_and_retains_value():
    definition = _payload_only_definition()
    runtime = build_buff_runtime(definition)
    runtime.apply(_apply_request(definition, (BuffModifierValue("test.payload.evidence", 1.55),)))
    record = runtime.buff_store.records[0]
    assert record.state.resolved_modifiers == ()
    assert [item.term_key for item in record.state.resolved_payloads] == ["test.payload.evidence"]
    assert record.state.resolved_payloads[0].value == pytest.approx(1.55)


def test_payload_only_definition_refresh_replaces_latest():
    definition = _payload_only_definition()
    runtime = build_buff_runtime(definition)
    runtime.apply(
        _apply_request(definition, (BuffModifierValue("test.payload.evidence", 1.0),), frame=10)
    )
    runtime.apply(
        _apply_request(definition, (BuffModifierValue("test.payload.evidence", 2.0),), frame=20)
    )
    record = runtime.buff_store.records[0]
    assert record.state.resolved_payloads[0].value == pytest.approx(2.0)


def test_payload_only_definition_keep_initial_refresh_keeps_value():
    definition = _payload_only_definition(value_refresh_policy=BuffValueRefreshPolicy.KEEP_INITIAL)
    runtime = build_buff_runtime(definition)
    runtime.apply(
        _apply_request(definition, (BuffModifierValue("test.payload.evidence", 1.0),), frame=10)
    )
    runtime.apply(
        _apply_request(definition, (BuffModifierValue("test.payload.evidence", 2.0),), frame=20)
    )
    record = runtime.buff_store.records[0]
    assert record.state.resolved_payloads[0].value == pytest.approx(1.0)


def test_payload_request_missing_value_rejected():
    definition = _payload_only_definition()
    runtime = build_buff_runtime(definition)
    with pytest.raises(BuffModifierBindingError, match="完整匹配模板"):
        runtime.apply(_apply_request(definition, ()))


def test_payload_request_unknown_value_rejected():
    definition = _payload_only_definition()
    runtime = build_buff_runtime(definition)
    with pytest.raises(BuffModifierBindingError, match="完整匹配模板"):
        runtime.apply(_apply_request(definition, (BuffModifierValue("test.payload.unknown", 1.0),)))


def test_payload_term_key_must_be_unique_across_modifier_and_payload():
    with pytest.raises(BuffValidationError, match="term_key 重复"):
        BuffDefinition(
            definition_key="buff.test.duplicate_term",
            mechanic_key=TEST_BUFF_MECHANIC_KEY,
            handler_key="test.buff",
            conflict_key="test.buff.duplicate_term",
            target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
            application_policy=BuffApplicationPolicy.REFRESH,
            value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
            max_stacks=1,
            attribute_modifiers=(
                BuffAttributeModifierTemplate(
                    term_key="test.duplicate.term",
                    target_key=STAT_ATK_TOTAL,
                    stage=ModifierStage.FLAT_ADD,
                ),
            ),
            payload_terms=(BuffPayloadTermTemplate(term_key="test.duplicate.term"),),
        )


def test_marker_only_definition_rejects_payload_terms():
    with pytest.raises(BuffValidationError, match="marker_only"):
        BuffDefinition(
            definition_key="buff.test.marker_payload",
            mechanic_key=TEST_BUFF_MECHANIC_KEY,
            handler_key="test.buff",
            conflict_key="test.buff.marker_payload",
            target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
            application_policy=BuffApplicationPolicy.REFRESH,
            value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
            max_stacks=1,
            marker_only=True,
            payload_terms=(BuffPayloadTermTemplate(term_key="test.payload.marker"),),
        )


def test_non_marker_definition_requires_modifier_or_payload_terms():
    with pytest.raises(BuffValidationError, match="attribute_modifiers 或 payload_terms"):
        BuffDefinition(
            definition_key="buff.test.empty_terms",
            mechanic_key=TEST_BUFF_MECHANIC_KEY,
            handler_key="test.buff",
            conflict_key="test.buff.empty_terms",
            target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
            application_policy=BuffApplicationPolicy.REFRESH,
            value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
            max_stacks=1,
        )


def test_mixed_definition_carries_both_channels():
    definition = _mixed_definition()
    runtime = build_buff_runtime(definition)
    runtime.apply(
        _apply_request(
            definition,
            (
                BuffModifierValue("test.mixed.atk", 30.0),
                BuffModifierValue("test.mixed.evidence", 1.5),
            ),
        )
    )
    record = runtime.buff_store.records[0]
    assert [item.term_key for item in record.state.resolved_modifiers] == ["test.mixed.atk"]
    assert [item.term_key for item in record.state.resolved_payloads] == ["test.mixed.evidence"]
    snapshot = BuffSnapshot.from_runtime(runtime, frame=10)
    instance = snapshot.instances[0]
    assert [item.term_key for item in instance.resolved_payloads] == ["test.mixed.evidence"]
    assert instance.resolved_payloads[0].value == pytest.approx(1.5)
    assert "resolved_payloads" in instance.to_dict()
