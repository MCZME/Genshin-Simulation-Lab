"""状态效果测试共享的纯构造器与常量。"""

from __future__ import annotations

from genshin_sim.core.attributes import (
    AttributeKey,
    AttributeSubjectKind,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.events import EventEngine
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffDefinitionRegistry,
    BuffResolver,
    BuffRuntime,
    BuffStore,
    BuffValueRefreshPolicy,
)

TEST_BUFF_MECHANIC_KEY = "mechanic.test.buff"
TEST_BUFF_HANDLER_KEY = "test.buff"
TEST_BUFF_SOURCE = RuntimeSourceRef(
    RuntimeSourceKind.MECHANIC,
    TEST_BUFF_MECHANIC_KEY,
    "player_team",
)


def build_buff_runtime(*definitions: BuffDefinition) -> BuffRuntime:
    """按定义集合构造内存 Buff 运行时；不绑定任何运行时端口。"""

    return BuffRuntime(
        definition_registry=BuffDefinitionRegistry(tuple(definitions)),
        buff_store=BuffStore(),
        resolver=BuffResolver(),
        event_engine=EventEngine(),
    )


def make_marker_buff_definition(
    *,
    kind: AttributeSubjectKind,
    definition_key: str,
    conflict_key: str,
    tags: frozenset[str] = frozenset(),
    display_name: str = "测试标记效果",
) -> BuffDefinition:
    """构造只作存在标记、不写属性词条的 Buff 定义。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=TEST_BUFF_MECHANIC_KEY,
        handler_key=TEST_BUFF_HANDLER_KEY,
        conflict_key=conflict_key,
        target_kinds=frozenset({kind}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        marker_only=True,
        tags=tags,
        display_name=display_name,
    )


def make_attribute_buff_definition(
    *,
    kind: AttributeSubjectKind,
    definition_key: str,
    conflict_key: str,
    term_key: str,
    target_key: AttributeKey,
    stage: ModifierStage,
    application_policy: BuffApplicationPolicy = BuffApplicationPolicy.REFRESH,
    display_name: str = "测试词条效果",
) -> BuffDefinition:
    """构造写单个属性词条的 Buff 定义。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=TEST_BUFF_MECHANIC_KEY,
        handler_key=TEST_BUFF_HANDLER_KEY,
        conflict_key=conflict_key,
        target_kinds=frozenset({kind}),
        application_policy=application_policy,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=term_key,
                target_key=target_key,
                stage=stage,
            ),
        ),
        display_name=display_name,
    )
