"""开发者测试内容包：仅在开发者模式下注册与可见。

本包内的内容实现与配套资产行数据由代码直接定义，不进入正式资产库；
`register_test_content_units` 是唯一注册入口，由
`content.bootstrap_content_units.create_default_content_unit_registry(developer_mode=True)`
按需调用。
"""

from genshin_sim.content.test.bootstrap_test_content_units import (
    register_test_content_units,
)
from genshin_sim.content.test.characters.reaction_probe import (
    TEST_A_ACTION_KEY,
    TEST_A_ASSET_KEY,
    TEST_A_HANDLER_KEY,
    TEST_A_IMPACT_KEY,
    TEST_B_ACTION_KEY,
    TEST_B_ASSET_KEY,
    TEST_B_HANDLER_KEY,
    TEST_B_IMPACT_KEY,
    create_test_a_content_unit,
    create_test_b_content_unit,
)
from genshin_sim.content.test.weapons.modifier_blade import (
    MODIFIER_BLADE_ASSET_KEY,
    MODIFIER_BLADE_HANDLER_KEY,
    create_modifier_blade_content_unit,
)

__all__ = [
    "MODIFIER_BLADE_ASSET_KEY",
    "MODIFIER_BLADE_HANDLER_KEY",
    "TEST_A_ACTION_KEY",
    "TEST_A_ASSET_KEY",
    "TEST_A_HANDLER_KEY",
    "TEST_A_IMPACT_KEY",
    "TEST_B_ACTION_KEY",
    "TEST_B_ASSET_KEY",
    "TEST_B_HANDLER_KEY",
    "TEST_B_IMPACT_KEY",
    "create_modifier_blade_content_unit",
    "create_test_a_content_unit",
    "create_test_b_content_unit",
    "register_test_content_units",
]
