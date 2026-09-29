"""桑多涅 P4「悠久的演算机关」数值来源的单元测试（合成资产数据，见测试规范 §3.2）。

官方文本：辉映下施放战技时若解算功率超过 50，第二枚棱晶弹造成原本 400%
伤害；解算功率每降低 10 点获得一层持续 60 秒的「改进战术」（至多 10 层）；
辉映下施放爆发时清空全部层数，光束造成原本 100% + 清除层数 × 10% 的伤害。

本文件锁定一件事：这些数值全部来自**资产被动第 4 层效果行**，而非内容代码
里的常量（``read_p4_asset_values`` 是该效果行的唯一解析入口）。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.effects import (
    read_p4_asset_values,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from tests.helpers import sandrone as sandrone_helpers


def test_p4_asset_row_is_the_single_source_of_values() -> None:
    # 资产被动第 4 层效果行：阈值 50、强化 400%、层数上限 10、持续 60s、
    # 每 10 点一层、光束基座 100%、每层 10%。解析按分量序取，不做默认值兜底。
    values = read_p4_asset_values(sandrone_helpers.p4_effect_params())
    assert values.power_threshold == pytest.approx(50.0)
    assert values.prism_boost_multiplier == pytest.approx(4.0)
    assert values.tactics_max_stacks == 10
    assert values.tactics_duration_frames == 60 * 60
    assert values.tactics_power_step == pytest.approx(10.0)
    assert values.beam_bonus_base_multiplier == pytest.approx(1.0)
    assert values.beam_bonus_per_stack == pytest.approx(0.1)


def test_p4_asset_row_rejects_missing_or_illegal_components() -> None:
    params = sandrone_helpers.p4_effect_params()
    components = params["components"]
    assert isinstance(components, tuple)
    with pytest.raises(ContentUnitValidationError, match="缺少第 4 个数值分量"):
        read_p4_asset_values({**params, "components": components[:3]})
    broken = list(components)
    broken[7] = {**broken[7], "values": (0.0,)}  # type: ignore[index]
    with pytest.raises(ContentUnitValidationError, match="功率步长必须为正数"):
        read_p4_asset_values({**params, "components": tuple(broken)})
    broken = list(components)
    broken[5] = {**broken[5], "values": (4.5,)}  # type: ignore[index]
    with pytest.raises(ContentUnitValidationError, match="层数上限必须是正整数"):
        read_p4_asset_values({**params, "components": tuple(broken)})
