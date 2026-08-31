"""反应探针测试角色：test_a 与 test_b 共用一套元素命中实现。"""

from genshin_sim.content.test.characters.reaction_probe.constants import (
    REACTION_PROBE_COMPONENT_KEY,
    REACTION_PROBE_CONTENT_VERSION,
    REACTION_PROBE_MAIN_ATTACK_TAG,
    TEST_A_ACTION_KEY,
    TEST_A_ASSET_KEY,
    TEST_A_DISPLAY_NAME_BY_KEY,
    TEST_A_ELEMENT_BY_KEY,
    TEST_A_HANDLER_KEY,
    TEST_A_IMPACT_KEY,
    TEST_B_ACTION_KEY,
    TEST_B_ASSET_KEY,
    TEST_B_DISPLAY_NAME_BY_KEY,
    TEST_B_ELEMENT_BY_KEY,
    TEST_B_HANDLER_KEY,
    TEST_B_IMPACT_KEY,
)
from genshin_sim.content.test.characters.reaction_probe.content import (
    create_test_a_content_unit,
    create_test_b_content_unit,
)

__all__ = [
    "REACTION_PROBE_COMPONENT_KEY",
    "REACTION_PROBE_CONTENT_VERSION",
    "REACTION_PROBE_MAIN_ATTACK_TAG",
    "TEST_A_ACTION_KEY",
    "TEST_A_ASSET_KEY",
    "TEST_A_DISPLAY_NAME_BY_KEY",
    "TEST_A_ELEMENT_BY_KEY",
    "TEST_A_HANDLER_KEY",
    "TEST_A_IMPACT_KEY",
    "TEST_B_ACTION_KEY",
    "TEST_B_ASSET_KEY",
    "TEST_B_DISPLAY_NAME_BY_KEY",
    "TEST_B_ELEMENT_BY_KEY",
    "TEST_B_HANDLER_KEY",
    "TEST_B_IMPACT_KEY",
    "create_test_a_content_unit",
    "create_test_b_content_unit",
]
