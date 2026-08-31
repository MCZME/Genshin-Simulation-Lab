"""开发者测试内容单元注册入口。

只在开发者模式下被 ``create_default_content_unit_registry`` 调用；
测试 handler_key 统一使用 ``testing.*`` 命名空间，与正式内容隔离。
"""

from __future__ import annotations

from genshin_sim.content.registries import ContentUnitRegistry
from genshin_sim.content.test.artifacts.modifier_set import (
    MODIFIER_SET_HANDLER_KEY,
    create_modifier_set_content_unit,
)
from genshin_sim.content.test.characters.reaction_probe import (
    TEST_A_HANDLER_KEY,
    TEST_B_HANDLER_KEY,
    create_test_a_content_unit,
    create_test_b_content_unit,
)
from genshin_sim.content.test.weapons.modifier_blade import (
    MODIFIER_BLADE_HANDLER_KEY,
    create_modifier_blade_content_unit,
)


def register_test_content_units(registry: ContentUnitRegistry) -> None:
    """把开发者测试内容单元工厂注册进给定注册表。"""

    registry.register_character_factory(
        TEST_A_HANDLER_KEY,
        create_test_a_content_unit,
    )
    registry.register_character_factory(
        TEST_B_HANDLER_KEY,
        create_test_b_content_unit,
    )
    registry.register_weapon_factory(
        MODIFIER_BLADE_HANDLER_KEY,
        create_modifier_blade_content_unit,
    )
    registry.register_artifact_factory(
        MODIFIER_SET_HANDLER_KEY,
        create_modifier_set_content_unit,
    )
