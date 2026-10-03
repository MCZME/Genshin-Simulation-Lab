"""奥黛塔 P5/P6 攻击力曲线效果行的读数与错位校验（合成资产数据，测试规范 §3.2）。

本文件锁定三件事：

1. **组件位映射**：P5 四分量（起算攻击力 / 步长 / 每档增伤 / 上限），P6 五分量
   （前两位为词条链接编号与辉映·星扩散窗口秒数，内容侧不消费）；
2. **折算端点**：步长线性折算 + 封顶（起算值以下为 0，上限处不再增长）；
3. **组件错位校验**：步长取到比例分量、比例与上限互换、分量缺位都在读数时失败，
   不静默折算出近零或超大加成。

槽位归属与 provider 接线由集成用例覆盖（``tests/integration/content/odette``）。
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from genshin_sim.content.characters.snezhnaya.odette.effects import (
    read_p5_authority_bonus,
    read_p6_base_bonus,
)
from genshin_sim.content.characters.snezhnaya.odette.modifiers import (
    authority_bonus_for_atk,
    stellar_base_bonus_for_atk,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from tests.helpers import odette as odette_helpers


def _params(values: tuple[float, ...]) -> dict[str, object]:
    """按合成资产效果行的组件结构把数值序列包装成 params。"""

    return {
        "components": tuple(
            {
                "source_param": f"number_{index}",
                "kind": "numeric",
                "format": "number",
                "values": (value,),
            }
            for index, value in enumerate(values, start=1)
        )
    }


def _p5(values: tuple[float, ...]):
    return read_p5_authority_bonus(_params(values))


def _p6(values: tuple[float, ...]):
    return read_p6_base_bonus(_params(values))


def test_p5_reads_threshold_step_rate_and_cap() -> None:
    # 合成 P5 行与真实资产行同构：1000 起算、每 100 点 +1.5%、至多 30%。
    bonus = read_p5_authority_bonus(odette_helpers.odette_effect_params("passive:5"))
    assert bonus.threshold_atk == pytest.approx(1000.0)
    assert bonus.per_100_atk == pytest.approx(100.0)
    assert bonus.bonus_rate == pytest.approx(0.015)
    assert bonus.cap == pytest.approx(0.3)


def test_p6_reads_step_rate_and_cap_after_leading_components() -> None:
    # 合成 P6 行与真实资产行同构：number_1 词条链接、number_2 窗口秒数、
    # number_3/4/5 为步长 / 每档增伤 / 上限。
    bonus = read_p6_base_bonus(odette_helpers.odette_effect_params("passive:6"))
    assert bonus.per_100_atk == pytest.approx(100.0)
    assert bonus.bonus_rate == pytest.approx(0.007)
    assert bonus.cap == pytest.approx(0.14)


def test_authority_bonus_scales_from_threshold_and_caps() -> None:
    bonus = _p5((1000.0, 100.0, 0.015, 0.3))
    # 起算值及以下为 0，不产生负加成。
    assert authority_bonus_for_atk(800.0, bonus) == pytest.approx(0.0)
    assert authority_bonus_for_atk(1000.0, bonus) == pytest.approx(0.0)
    # 超过起算值的部分每 100 点 +1.5%（1400 -> 4 档 = 6%）。
    assert authority_bonus_for_atk(1400.0, bonus) == pytest.approx(0.06)
    # 2500 -> 15 档 = 22.5%（未封顶）；3000 起封顶 30%。
    assert authority_bonus_for_atk(2500.0, bonus) == pytest.approx(0.225)
    assert authority_bonus_for_atk(3000.0, bonus) == pytest.approx(0.3)
    assert authority_bonus_for_atk(5000.0, bonus) == pytest.approx(0.3)


def test_base_bonus_scales_from_zero_and_caps() -> None:
    bonus = _p6((1.0, 8.0, 100.0, 0.007, 0.14))
    assert stellar_base_bonus_for_atk(0.0, bonus) == pytest.approx(0.0)
    # 200 攻击 -> 2 档 = 1.4%；2000 攻击即封顶 14%。
    assert stellar_base_bonus_for_atk(200.0, bonus) == pytest.approx(0.014)
    assert stellar_base_bonus_for_atk(2000.0, bonus) == pytest.approx(0.14)
    assert stellar_base_bonus_for_atk(5000.0, bonus) == pytest.approx(0.14)


def test_p6_legacy_component_layout_fails() -> None:
    # 旧合成行把链接与窗口秒数省掉（3 分量）：上限位缺位必须在读数时失败，
    # 而不是把 0.14 当成步长折算。
    with pytest.raises(ContentUnitValidationError):
        _p6((100.0, 0.007, 0.14))


def test_p6_swapped_step_and_rate_fails() -> None:
    # 步长取到比例分量（0.007 < 1）：文本「每 N 点」的 N 是计数。
    with pytest.raises(ContentUnitValidationError):
        _p6((1.0, 8.0, 0.007, 100.0, 0.14))


def test_p6_swapped_rate_and_cap_fails() -> None:
    # 比例与上限互换：上限不再是每档增伤的整数倍。
    with pytest.raises(ContentUnitValidationError):
        _p6((1.0, 8.0, 100.0, 0.14, 0.007))


def test_p5_swapped_step_and_rate_fails() -> None:
    with pytest.raises(ContentUnitValidationError):
        _p5((1000.0, 0.015, 100.0, 0.3))


def test_p5_swapped_rate_and_cap_fails() -> None:
    with pytest.raises(ContentUnitValidationError):
        _p5((1000.0, 100.0, 0.3, 0.015))


def test_p5_missing_cap_fails() -> None:
    with pytest.raises(ContentUnitValidationError):
        _p5((1000.0, 100.0, 0.015))


def test_effect_params_helper_rejects_unknown_row() -> None:
    with pytest.raises(AssertionError):
        odette_helpers.odette_effect_params("passive:99")


def test_effect_params_returns_mapping() -> None:
    params: Mapping[str, object] = odette_helpers.odette_effect_params("passive:6")
    assert params["name"] == "合成天赋6"
