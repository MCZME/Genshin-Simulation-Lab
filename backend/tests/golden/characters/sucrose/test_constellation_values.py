"""砂糖命座 C1–C6 数值 golden 基线。

验证能力：六层命座的已确认数值常量、C4 触发面、C6 魔导增强常量，以及
C2 窗口延长后大型风灵时序的同源派生。
资料来源及适用版本：源站 meropide.cn/en/characters/Sucrose 的
``constellation`` 原文（纳塔 5.x 数据版本）；C2 拍数 4 拍、C4 随机 1–7
整数秒均匀分布（7 点各 1/7）、C6 含砂糖自己与魔导增强 +8.57142% 均为
实施规划 §11.6 裁决；C6 魔导增强取源站 ``descriptionBuff``（该字段不
导入资产库，数值按裁决由内容侧常量定义、不做分数化简）。
完整输入条件：无常量输入——本文件冻结的是内容数据真值。
预期输出与允许误差：整数帧 / 比例值精确比较（1e-9）。
不覆盖的行为：充能 / 计次 / 随机源 / Buff 投放等运行期行为（集成测试
承担）；资产效果行数值本身（资产库承担）。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_C1_EXTRA_CHARGES,
    SUCROSE_C2_EXTRA_SECONDS,
    SUCROSE_C3_TALENT_BOOST,
    SUCROSE_C3_TALENT_CAP,
    SUCROSE_C4_COUNT_INTERVAL_FRAMES,
    SUCROSE_C4_MAX_REDUCTION_SECONDS,
    SUCROSE_C4_MIN_REDUCTION_SECONDS,
    SUCROSE_C4_TRIGGER_HIT_COUNT,
    SUCROSE_C4_TRIGGER_MAIN_ATTACK_TAGS,
    SUCROSE_C5_TALENT_BOOST,
    SUCROSE_C5_TALENT_CAP,
    SUCROSE_C6_DAMAGE_BONUS,
    SUCROSE_C6_MAGE_ENHANCEMENT_BONUS,
)
from genshin_sim.content.characters.mondstadt.sucrose.spirit import resolve_spirit_timing


def test_c1_and_c2_values():
    """C1：E 可使用次数 +1；C2：Q 技能持续时间 +2s。"""

    assert SUCROSE_C1_EXTRA_CHARGES == 1
    assert SUCROSE_C2_EXTRA_SECONDS == 2


def test_c3_and_c5_talent_boosts():
    """C3 / C5：E / Q 等级 +3、至多 15 级（源站 talentIndex 2 / 9）。"""

    assert (SUCROSE_C3_TALENT_BOOST, SUCROSE_C3_TALENT_CAP) == (3, 15)
    assert (SUCROSE_C5_TALENT_BOOST, SUCROSE_C5_TALENT_CAP) == (3, 15)


def test_c4_values():
    """C4：命中 7 次触发、随机减 1–7 秒、计次间隔 0.1s = 6 帧。

    触发面为普攻四段与重击（源站「普通攻击或重击命中敌人」，不含下落）。
    """

    assert SUCROSE_C4_TRIGGER_HIT_COUNT == 7
    assert SUCROSE_C4_MIN_REDUCTION_SECONDS == 1
    assert SUCROSE_C4_MAX_REDUCTION_SECONDS == 7
    assert SUCROSE_C4_COUNT_INTERVAL_FRAMES == 6
    assert SUCROSE_C4_TRIGGER_MAIN_ATTACK_TAGS == (
        "普通攻击1",
        "普通攻击2",
        "普通攻击3",
        "普通攻击4",
        "重击",
    )


def test_c4_reduction_frames_are_seven_equally_spaced_values():
    """随机减冷却的 7 个可能值 = 1–7 整数秒（60–420 帧，各 1/7）。"""

    reduction_seconds = range(
        SUCROSE_C4_MIN_REDUCTION_SECONDS, SUCROSE_C4_MAX_REDUCTION_SECONDS + 1
    )
    assert [seconds * 60 for seconds in reduction_seconds] == [60, 120, 180, 240, 300, 360, 420]


def test_c6_values():
    """C6：染色后全队（含砂糖）对应元素伤害 +20%；魔导增强 +8.57142%。"""

    assert pytest.approx(0.2, rel=0.0, abs=1e-9) == SUCROSE_C6_DAMAGE_BONUS
    assert pytest.approx(0.0857142, rel=0.0, abs=1e-9) == SUCROSE_C6_MAGE_ENHANCEMENT_BONUS


@pytest.mark.parametrize(
    ("extra_seconds", "expected"),
    [
        (0, (360, 361, 3)),
        (2, (480, 481, 4)),
    ],
    ids=("base_6s", "c2_8s"),
)
def test_resolve_spirit_timing_derives_window_lifetime_and_ticks(extra_seconds, expected):
    """C2 同源派生：0 → 6s 窗口 / 361 生命周期 / 3 拍；2 → 8s / 481 / 4 拍。

    窗口 = 6s + 延长秒数；生命周期 = 窗口 + 1（端点判据组合，见帧表基线）；
    拍数 = 窗口 / 120。
    """

    window, lifetime, tick_count = resolve_spirit_timing(extra_seconds)
    assert (window, lifetime, tick_count) == expected
