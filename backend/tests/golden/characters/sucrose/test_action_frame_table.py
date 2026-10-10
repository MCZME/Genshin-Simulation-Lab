"""砂糖动作帧表 golden 基线。

验证能力：砂糖全部动作的时长、命中帧、最早衔接帧与冷却起始帧（内容常量
``SUCROSE_ACTION_TABLE`` 及相关帧常量逐位冻结）。
资料来源及适用版本：维护者提供的动作帧表与动作衔接表（实施规划 §4.4，
60fps；§4.5 裁决：与 KQM 抓取不一致处一律取维护者数据）；元素战技冷却
15s、元素爆发冷却 20s / 能量花费帧 21 取资产倍率条目（源站
meropide.cn/en/characters/Sucrose，纳塔 5.x 数据版本）。
完整输入条件：无常量输入——本文件冻结的是内容数据真值。
预期输出与允许误差：整数帧逐位相等。
不覆盖的行为：动作解释器对帧表的运行期消费（集成测试承担）；倍率数值
（资产库承担，不进 golden）。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ACTION_TABLE,
    SUCROSE_CHARGED_ATTACK_ACTION_KEY,
    SUCROSE_ELEMENTAL_BURST_ACTION_KEY,
    SUCROSE_ELEMENTAL_BURST_COOLDOWN_FRAMES,
    SUCROSE_ELEMENTAL_BURST_COOLDOWN_START_FRAME,
    SUCROSE_ELEMENTAL_BURST_CREATE_FRAME,
    SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_FRAME,
    SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    SUCROSE_ELEMENTAL_SKILL_ACTION_KEY,
    SUCROSE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
    SUCROSE_ELEMENTAL_SKILL_COOLDOWN_START_FRAME,
    SUCROSE_ELEMENTAL_SKILL_HIT_FRAME,
    SUCROSE_NORMAL_ATTACK_1_ACTION_KEY,
    SUCROSE_NORMAL_ATTACK_2_ACTION_KEY,
    SUCROSE_NORMAL_ATTACK_3_ACTION_KEY,
    SUCROSE_NORMAL_ATTACK_4_ACTION_KEY,
    SUCROSE_SPIRIT_CREATE_IMPACT_KEY,
    SUCROSE_SPIRIT_DURATION_FRAMES,
    SUCROSE_SPIRIT_TICK_COUNT,
    SUCROSE_SPIRIT_TICK_PERIOD_FRAMES,
    SUCROSE_SPIRIT_WINDOW_FRAMES,
)


def test_normal_attack_frames():
    """普攻四段：时长 / 命中帧 / 普攻与重击的最早衔接帧。"""

    expected = {
        SUCROSE_NORMAL_ATTACK_1_ACTION_KEY: (
            21,
            14,
            {("normal_attack", 21), ("charged_attack", 2)},
        ),
        SUCROSE_NORMAL_ATTACK_2_ACTION_KEY: (
            26,
            18,
            {("normal_attack", 26), ("charged_attack", 4)},
        ),
        SUCROSE_NORMAL_ATTACK_3_ACTION_KEY: (
            33,
            27,
            {("normal_attack", 33), ("charged_attack", 16)},
        ),
        SUCROSE_NORMAL_ATTACK_4_ACTION_KEY: (
            51,
            28,
            {("normal_attack", 51), ("charged_attack", 42)},
        ),
    }
    for action_key, (duration, hit_frame, transitions) in expected.items():
        spec = SUCROSE_ACTION_TABLE[action_key]
        assert spec.duration_frames == duration, action_key
        assert spec.hit_frame == hit_frame, action_key
        assert {(key, frame) for key, frame in spec.transitions.items()} == transitions, action_key


def test_charged_attack_frames():
    """重击：时长 69、命中帧 54、五向衔接帧。"""

    spec = SUCROSE_ACTION_TABLE[SUCROSE_CHARGED_ATTACK_ACTION_KEY]
    assert spec.duration_frames == 69
    assert spec.hit_frame == 54
    assert spec.transitions == {
        "normal_attack": 69,
        "charged_attack": 66,
        "elemental_skill": 60,
        "elemental_burst": 61,
        "jump": 53,
    }


def test_elemental_skill_frames():
    """元素战技：时长 57、命中帧 42、CD 15s = 900 帧、CD 起始帧 9。"""

    spec = SUCROSE_ACTION_TABLE[SUCROSE_ELEMENTAL_SKILL_ACTION_KEY]
    assert spec.duration_frames == 57
    assert spec.hit_frame == SUCROSE_ELEMENTAL_SKILL_HIT_FRAME == 42
    assert spec.cooldown_ability_key == "elemental_skill"
    assert spec.cooldown_start_frame == SUCROSE_ELEMENTAL_SKILL_COOLDOWN_START_FRAME == 9
    assert SUCROSE_ELEMENTAL_SKILL_COOLDOWN_FRAMES == 900


def test_elemental_burst_frames():
    """元素爆发：时长 49、创建帧 17、能量花费帧 21、CD 20s = 1200 帧、起始帧 18。"""

    spec = SUCROSE_ACTION_TABLE[SUCROSE_ELEMENTAL_BURST_ACTION_KEY]
    assert spec.duration_frames == 49
    assert spec.hit_frame is None
    assert {(point.impact_key, point.frame) for point in spec.impact_points} == {
        (SUCROSE_SPIRIT_CREATE_IMPACT_KEY, 17),
        (SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY, 21),
    }
    assert SUCROSE_ELEMENTAL_BURST_CREATE_FRAME == 17
    assert SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_FRAME == 21
    assert spec.cooldown_ability_key == "elemental_burst"
    assert spec.cooldown_start_frame == SUCROSE_ELEMENTAL_BURST_COOLDOWN_START_FRAME == 18
    assert SUCROSE_ELEMENTAL_BURST_COOLDOWN_FRAMES == 1200


def test_spirit_timing_frames():
    """大型风灵时序：120 帧一拍、3 拍、窗口 360 帧（6s）、生命周期 361 帧。

    生命周期 = 窗口 + 1 是项目端点判据（``frame < 创建帧 + 生命周期`` 不含
    端点帧）与「第三拍落在窗口端点」的组合结果，不是独立时长取值。
    """

    assert SUCROSE_SPIRIT_TICK_PERIOD_FRAMES == 120
    assert SUCROSE_SPIRIT_TICK_COUNT == 3
    assert SUCROSE_SPIRIT_WINDOW_FRAMES == 360
    assert SUCROSE_SPIRIT_DURATION_FRAMES == SUCROSE_SPIRIT_WINDOW_FRAMES + 1 == 361
