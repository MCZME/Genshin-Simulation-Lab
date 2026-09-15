# 单一关注点：队伍作用域 Buff 记录的主体读取、刷新、冲突隔离与移除生命周期。
from __future__ import annotations

from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
)
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationOutcome,
    BuffApplicationPolicy,
    BuffDefinition,
    BuffModifierValue,
)
from tests.helpers.buff import (
    TEST_BUFF_SOURCE,
    build_buff_runtime,
    make_attribute_buff_definition,
    make_marker_buff_definition,
)

# 两个队伍作用域 kind 共用同一个队伍稳定作用域 id 作为挂载身份。
TEAM = AttributeSubjectRef.team("player_team")
ACTIVE_CHARACTER = AttributeSubjectRef.active_character("player_team")
TEAM_OTHER = AttributeSubjectRef.team("other_team")
CHARACTER = AttributeSubjectRef.character("character:slot_1")


def _team_marker_definition() -> BuffDefinition:
    return make_marker_buff_definition(
        kind=AttributeSubjectKind.TEAM,
        definition_key="buff.test.team_scope_effect",
        conflict_key="test.buff.conflict.team_scope_effect",
        tags=frozenset({"test_team_buff"}),
    )


def _active_character_marker_definition() -> BuffDefinition:
    return make_marker_buff_definition(
        kind=AttributeSubjectKind.ACTIVE_CHARACTER,
        definition_key="buff.test.active_character_scope_effect",
        conflict_key="test.buff.conflict.active_character_scope_effect",
    )


def _character_definition() -> BuffDefinition:
    return make_attribute_buff_definition(
        kind=AttributeSubjectKind.CHARACTER,
        definition_key="buff.test.character_scope_effect",
        conflict_key="test.buff.conflict.character_scope_effect",
        term_key="atk_bonus",
        target_key=STAT_ATK_TOTAL,
        stage=ModifierStage.PERCENT_ADD,
        application_policy=BuffApplicationPolicy.REPLACE,
    )


def _request(
    request_id: str,
    definition: BuffDefinition,
    *,
    frame: int = 0,
    target_ref: AttributeSubjectRef = TEAM,
    duration: int = 10,
) -> ApplyBuffRequest:
    modifier_values = (
        ()
        if definition.marker_only
        else tuple(
            BuffModifierValue(template.term_key, 0.1) for template in definition.attribute_modifiers
        )
    )
    return ApplyBuffRequest(
        request_id=request_id,
        frame=frame,
        order=0,
        definition_key=definition.definition_key,
        target_ref=target_ref,
        source_context=TEST_BUFF_SOURCE,
        duration_frames=duration,
        modifier_values=modifier_values,
    )


def test_team_scope_records_are_isolated_per_subject():
    """队伍作用域记录按主体隔离：读取与冲突都不跨 kind 串扰。"""

    team_definition = _team_marker_definition()
    active_definition = _active_character_marker_definition()
    character_definition = _character_definition()
    runtime = build_buff_runtime(team_definition, active_definition, character_definition)
    team_key = team_definition.definition_key
    active_key = active_definition.definition_key

    team_result = runtime.apply(_request("team:1", team_definition, frame=0, duration=10))
    active_result = runtime.apply(
        _request("active:1", active_definition, frame=0, target_ref=ACTIVE_CHARACTER, duration=10)
    )
    character_result = runtime.apply(
        _request("character:1", character_definition, target_ref=CHARACTER, duration=10)
    )

    # 同一 conflict key 在三个主体上互不冲突，各持独立实例。
    assert (
        len({team_result.instance_ref, active_result.instance_ref, character_result.instance_ref})
        == 3
    )
    assert runtime.buff_store.require(team_result.instance_ref).state.target_ref == TEAM
    assert (
        runtime.buff_store.require(active_result.instance_ref).state.target_ref == ACTIVE_CHARACTER
    )

    assert runtime.reader.active(0, target_ref=TEAM, definition_key=team_key)
    assert runtime.reader.active(0, target_ref=ACTIVE_CHARACTER, definition_key=active_key)
    assert not runtime.reader.active(0, target_ref=TEAM_OTHER, definition_key=team_key)
    # 两个队伍作用域 kind 与固定角色主体三者互不串读。
    assert not runtime.reader.active(0, target_ref=ACTIVE_CHARACTER, definition_key=team_key)
    assert not runtime.reader.active(0, target_ref=TEAM, definition_key=active_key)
    assert not runtime.reader.active(0, target_ref=CHARACTER, definition_key=active_key)


def test_team_scope_buff_refresh_reuses_generic_rules():
    """队伍作用域主体复用通用 REFRESH：只延长存在时间、实例引用不变。"""

    definition = _active_character_marker_definition()
    runtime = build_buff_runtime(definition)

    first = runtime.apply(
        _request("active:1", definition, frame=0, target_ref=ACTIVE_CHARACTER, duration=10)
    )
    refreshed = runtime.apply(
        _request("active:2", definition, frame=4, target_ref=ACTIVE_CHARACTER, duration=10)
    )
    assert refreshed.outcome is BuffApplicationOutcome.REFRESHED
    assert refreshed.instance_ref == first.instance_ref
    record = runtime.buff_store.require(first.instance_ref)
    assert (record.created_frame, record.last_applied_frame) == (0, 4)
    assert record.expires_at_frame == 14
