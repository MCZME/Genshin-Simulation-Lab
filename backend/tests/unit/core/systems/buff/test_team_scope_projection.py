# 单一关注点：队伍作用域 Buff 记录向角色属性查询的投影。
from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectKind,
    AttributeSubjectRef,
    BaseAttributeSet,
    ModifierProviderIndex,
    ModifierStage,
    create_public_attribute_registry,
)
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffAttributeModifierProvider,
    BuffDefinition,
    BuffModifierValue,
    BuffRuntime,
    BuffStoreReader,
)
from tests.helpers.buff import (
    TEST_BUFF_SOURCE,
    build_buff_runtime,
    make_attribute_buff_definition,
)

TEAM_REF = "player_team"


class _FakeProjectionPort:
    """最小投影端口：只有队伍内两个槽位，slot_1 为当前场上角色。"""

    def __init__(self, *, team_ref: str = TEAM_REF, active_entity_id: str = "character:slot_1"):
        self._team_ref = team_ref
        self._active_entity_id = active_entity_id
        self._members = ("character:slot_1", "character:slot_2")

    def team_scope_for(self, character_ref: AttributeSubjectRef) -> str | None:
        if character_ref.entity_id not in self._members:
            return None
        return self._team_ref

    def is_active_character(self, character_ref: AttributeSubjectRef) -> bool:
        return character_ref.entity_id == self._active_entity_id


def _definition(kind: AttributeSubjectKind, *, definition_key: str) -> BuffDefinition:
    return make_attribute_buff_definition(
        kind=kind,
        definition_key=definition_key,
        conflict_key=f"test.conflict.{definition_key}",
        term_key="elemental_mastery",
        target_key=STAT_ELEMENTAL_MASTERY,
        stage=ModifierStage.FLAT_ADD,
    )


def _apply(
    runtime: BuffRuntime,
    definition: BuffDefinition,
    target_ref: AttributeSubjectRef,
    *,
    value: float = 30.0,
    duration: int = 360,
    frame: int = 0,
) -> None:
    runtime.apply(
        ApplyBuffRequest(
            request_id=f"req:{definition.definition_key}:{target_ref.entity_id}:{target_ref.kind}",
            frame=frame,
            order=0,
            definition_key=definition.definition_key,
            target_ref=target_ref,
            source_context=TEST_BUFF_SOURCE,
            duration_frames=duration,
            modifier_values=(BuffModifierValue("elemental_mastery", value),),
        )
    )


def _resolve(
    runtime: BuffRuntime,
    definition: BuffDefinition,
    subject_ref: AttributeSubjectRef,
    *,
    port: _FakeProjectionPort | None,
    frame: int = 0,
) -> float:
    registry = create_public_attribute_registry()
    provider = BuffAttributeModifierProvider(definition, BuffStoreReader(runtime.buff_store))
    if port is not None:
        provider.bind_runtime_ports(team_scope_projection_port=port)
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(()),
        modifier_index=ModifierProviderIndex((provider,), registry=registry),
    )
    resolution = resolver.resolve(
        AttributeQuery(
            subject_ref,
            STAT_ELEMENTAL_MASTERY,
            frame=frame,
        )
    )
    return resolution.final_value


def test_team_scope_record_increases_every_team_member_panel():
    definition = _definition(AttributeSubjectKind.TEAM, definition_key="buff.test.team_projection")
    runtime = build_buff_runtime(definition)
    _apply(runtime, definition, AttributeSubjectRef.team(TEAM_REF), value=30.0)
    port = _FakeProjectionPort()

    assert _resolve(
        runtime, definition, AttributeSubjectRef.character("character:slot_1"), port=port
    ) == pytest.approx(30.0)
    assert _resolve(
        runtime, definition, AttributeSubjectRef.character("character:slot_2"), port=port
    ) == pytest.approx(30.0)


def test_team_scope_record_does_not_apply_without_projection_port():
    definition = _definition(
        AttributeSubjectKind.TEAM, definition_key="buff.test.team_projection.noport"
    )
    runtime = build_buff_runtime(definition)
    _apply(runtime, definition, AttributeSubjectRef.team(TEAM_REF), value=30.0)

    # 未绑定投影端口时退回精确主体匹配：角色查询读不到队伍作用域记录。
    assert _resolve(
        runtime,
        definition,
        AttributeSubjectRef.character("character:slot_1"),
        port=None,
    ) == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("active_entity_id", "expected"),
    (
        ("character:slot_1", {"character:slot_1": 30.0, "character:slot_2": 0.0}),
        ("character:slot_2", {"character:slot_1": 0.0, "character:slot_2": 30.0}),
    ),
    ids=("active_slot_1", "active_slot_2"),
)
def test_active_character_record_only_projects_onto_current_active_character(
    active_entity_id: str,
    expected: dict[str, float],
):
    definition = _definition(
        AttributeSubjectKind.ACTIVE_CHARACTER,
        definition_key="buff.test.active_character_projection",
    )
    runtime = build_buff_runtime(definition)
    _apply(runtime, definition, AttributeSubjectRef.active_character(TEAM_REF), value=30.0)
    port = _FakeProjectionPort(active_entity_id=active_entity_id)

    for entity_id, value in expected.items():
        assert _resolve(
            runtime,
            definition,
            AttributeSubjectRef.character(entity_id),
            port=port,
        ) == pytest.approx(value)


@pytest.mark.parametrize(
    ("kind", "target_ref"),
    (
        (AttributeSubjectKind.CHARACTER, AttributeSubjectRef.character("character:slot_1")),
        (AttributeSubjectKind.TARGET, AttributeSubjectRef.target("target:1")),
    ),
    ids=("character", "target"),
)
def test_non_team_scope_records_do_not_project_onto_other_subjects(
    kind: AttributeSubjectKind,
    target_ref: AttributeSubjectRef,
):
    definition = _definition(kind, definition_key=f"buff.test.{kind.value}_projection")
    runtime = build_buff_runtime(definition)
    _apply(runtime, definition, target_ref, value=30.0)
    port = _FakeProjectionPort()

    # 记录只作用于精确匹配的主体：其它角色读不到，target 主体也不投影到角色。
    for entity_id in ("character:slot_1", "character:slot_2"):
        expected = 30.0 if entity_id == target_ref.entity_id else 0.0
        assert _resolve(
            runtime,
            definition,
            AttributeSubjectRef.character(entity_id),
            port=port,
        ) == pytest.approx(expected)


def test_team_and_active_character_records_stack_on_active_member():
    team_definition = _definition(AttributeSubjectKind.TEAM, definition_key="buff.test.stack.team")
    active_definition = _definition(
        AttributeSubjectKind.ACTIVE_CHARACTER, definition_key="buff.test.stack.active"
    )
    runtime = build_buff_runtime(team_definition, active_definition)
    _apply(runtime, team_definition, AttributeSubjectRef.team(TEAM_REF), value=30.0)
    _apply(runtime, active_definition, AttributeSubjectRef.active_character(TEAM_REF), value=20.0)

    registry = create_public_attribute_registry()
    team_provider = BuffAttributeModifierProvider(
        team_definition, BuffStoreReader(runtime.buff_store)
    )
    active_provider = BuffAttributeModifierProvider(
        active_definition, BuffStoreReader(runtime.buff_store)
    )
    port = _FakeProjectionPort(active_entity_id="character:slot_1")
    for provider in (team_provider, active_provider):
        provider.bind_runtime_ports(team_scope_projection_port=port)
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(()),
        modifier_index=ModifierProviderIndex((team_provider, active_provider), registry=registry),
    )

    def value_for(entity_id: str) -> float:
        return resolver.resolve(
            AttributeQuery(
                AttributeSubjectRef.character(entity_id),
                STAT_ELEMENTAL_MASTERY,
                frame=0,
            )
        ).final_value

    # 当前场上角色同时吃到队伍与位置级两份；后台角色只吃队伍一份。
    assert value_for("character:slot_1") == pytest.approx(50.0)
    assert value_for("character:slot_2") == pytest.approx(30.0)
