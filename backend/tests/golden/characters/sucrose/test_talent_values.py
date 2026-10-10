"""砂糖固有天赋与魔导强化数值 golden 基线。

验证能力：A1「触媒置换术」、A4「小小的慧风」与「魔女的前夜礼·七循之理」
（passive:9）的已确认数值常量与触发面。
资料来源及适用版本：源站 meropide.cn/en/characters/Sucrose 的
``passive:4`` / ``passive:5`` / ``passive:9``（纳塔 5.x 数据版本）；
A1 含星扩散为维护者裁决（实施规划 §8 第 3 项），「A4 快照砂糖精通」与
「前夜礼 ≥2 名魔导角色激活」为实施规划 §11.5 / §11.7 裁决。
完整输入条件：无常量输入——本文件冻结的是内容数据真值。
预期输出与允许误差：比例值精确比较（1e-9）；时长为整数帧。
不覆盖的行为：buff 投放 / 刷新 / 冲突等运行期行为（集成测试承担）；
资产效果行数值本身（资产库承担）。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_A1_DURATION_FRAMES,
    SUCROSE_A1_MASTERY_FLAT,
    SUCROSE_A1_TRIGGER_REACTION_KEYS,
    SUCROSE_A4_DURATION_FRAMES,
    SUCROSE_A4_MASTERY_RATIO,
    SUCROSE_A4_TRIGGER_MAIN_ATTACK_TAGS,
    SUCROSE_WITCHES_EVE_LARGE_BONUS,
    SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES,
    SUCROSE_WITCHES_EVE_MIN_MAGE_COUNT,
    SUCROSE_WITCHES_EVE_SMALL_BONUS,
    SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import SWIRL_REACTION_KEY


def test_a1_catalyst_conversion_values():
    """A1：扩散 / 星扩散触发，对应元素角色精通 +50、8s。"""

    assert pytest.approx(50.0, rel=0.0, abs=1e-9) == SUCROSE_A1_MASTERY_FLAT
    assert SUCROSE_A1_DURATION_FRAMES == 8 * 60


def test_a1_trigger_reactions_include_stellar_swirl():
    """A1 触发面：普通扩散与星扩散（维护者裁决，资产文本为未更新旧版）。"""

    assert (
        frozenset({SWIRL_REACTION_KEY, STELLAR_SWIRL_REACTION_KEY})
        == SUCROSE_A1_TRIGGER_REACTION_KEYS
    )


def test_a4_mollis_favonius_values():
    """A4：战技 / 爆发命中触发，全队（除砂糖）精通 +20%（快照）、8s。"""

    assert pytest.approx(0.2, rel=0.0, abs=1e-9) == SUCROSE_A4_MASTERY_RATIO
    assert SUCROSE_A4_DURATION_FRAMES == 8 * 60
    assert frozenset({"元素战技", "元素爆发"}) == SUCROSE_A4_TRIGGER_MAIN_ATTACK_TAGS


def test_witches_eve_values():
    """前夜礼：≥2 名魔导角色激活；小型 15s / 5.71428%，大型 20s / 7.14285%。

    数值直接使用源站口径、不做分数化简（实施规划 §11.7 裁决 6 / 7）。
    """

    assert SUCROSE_WITCHES_EVE_MIN_MAGE_COUNT == 2
    assert SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES == 15 * 60
    assert pytest.approx(0.0571428, rel=0.0, abs=1e-9) == SUCROSE_WITCHES_EVE_SMALL_BONUS
    assert SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES == 20 * 60
    assert pytest.approx(0.0714285, rel=0.0, abs=1e-9) == SUCROSE_WITCHES_EVE_LARGE_BONUS
