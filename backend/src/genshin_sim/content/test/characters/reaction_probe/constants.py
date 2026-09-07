"""反应探针测试内容：稳定键与按键元素映射。

test_a 与 test_b 共用同一套动作与命中实现，只通过各自元素表区分职责：

- test_a（火/冰/草/岩）：触发蒸发（火侧）、融化、燃烧、结晶、蔓激化、烈绽放；
- test_b（水/雷/风/物理）：触发蒸发（水侧）、超载、超导、冻结、碎冰、感电、
  扩散、原激化、超激化、绽放、超绽放。

所有命中使用弱 1 GU 元素预算（物理不携带元素、风/岩不形成持久 Aura），
ICD 不绑定，保证输入轨迹可以按任意顺序逐帧编排，避免反应之间相互干扰。
所有数值均为测试固定值，不代表任何真实游戏数据。
"""

from __future__ import annotations

from genshin_sim.core.elements import Element

REACTION_PROBE_CONTENT_VERSION = "dev-reaction-probe"
REACTION_PROBE_COMPONENT_KEY = "atk.main"
REACTION_PROBE_MAIN_ATTACK_TAG = "testing.reaction_probe.direct"

TEST_A_HANDLER_KEY = "character.testing.test_a"
TEST_B_HANDLER_KEY = "character.testing.test_b"
TEST_A_ASSET_KEY = "character:test_a"
TEST_B_ASSET_KEY = "character:test_b"
TEST_A_ACTION_KEY = "character.testing.test_a.action"
TEST_B_ACTION_KEY = "character.testing.test_b.action"
TEST_A_IMPACT_KEY = "character.testing.test_a.impact"
TEST_B_IMPACT_KEY = "character.testing.test_b.impact"

# 按键 -> 命中元素。火/水/冰/雷/草携带弱附着；风/岩携带正元素预算但不形成
# 持久 Aura；物理不携带元素且为钝击（碎冰用）。
TEST_A_ELEMENT_BY_KEY: dict[str, Element] = {
    "mouse.left": Element.PYRO,
    "mouse.right": Element.CRYO,
    "keyboard.e": Element.DENDRO,
    "keyboard.q": Element.GEO,
}
TEST_B_ELEMENT_BY_KEY: dict[str, Element] = {
    "mouse.left": Element.HYDRO,
    "mouse.right": Element.ELECTRO,
    "keyboard.e": Element.ANEMO,
    "keyboard.q": Element.PHYSICAL,
}

# 按键 -> 命中显示名（进入 DAMAGE_RESOLVED 审计的 damage_name）。
TEST_A_DISPLAY_NAME_BY_KEY: dict[str, str] = {
    "mouse.left": "探针A·火",
    "mouse.right": "探针A·冰",
    "keyboard.e": "探针A·草",
    "keyboard.q": "探针A·岩",
}
TEST_B_DISPLAY_NAME_BY_KEY: dict[str, str] = {
    "mouse.left": "探针B·水",
    "mouse.right": "探针B·雷",
    "keyboard.e": "探针B·风",
    "keyboard.q": "探针B·物",
}
