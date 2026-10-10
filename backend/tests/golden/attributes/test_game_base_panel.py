"""游戏规则基础面板值 golden 基线。

验证能力：每个角色在没有任何资产/内容侧配置时，也应具备游戏全局规则给定的基础面板——
暴击率 ``5%``、暴击伤害 ``50%``、元素充能效率 ``100%``——且这三项按**绝对值**存储
与消费（见[属性系统契约](../../../docs/契约/属性系统契约.md)第 4.3 节）。
这是需要长期保证的不变量：**下游公式不再补基底**（伤害侧暴击乘数直接用
``1 + crit_damage``，能量侧充能倍率直接取效率本身），因此基础值一旦从属性侧丢失，
暴击乘数会少 ``0.5``、充能倍率会少 ``1.0``。

真实数据来源及适用版本：

- 三项基础面板值是游戏全局规则（所有角色共有），不是角色/武器资产数据：暴击率 5%、
  暴击伤害 50%、元素充能效率 100%。注入通道遵循属性系统契约第 9 节「基础贡献」，
  不用 ``AttributeDefinition.default_value``（第 7.1 节禁止其承载游戏规则默认面板）。
- 常量单点定义：``core/attributes/base_stats.py`` 的 ``GAME_BASE_CRIT_RATE`` /
  ``GAME_BASE_CRIT_DAMAGE`` / ``GAME_BASE_ENERGY_RECHARGE`` 与
  ``GAME_BASE_CHARACTER_PANEL``。

预期输出与允许误差：三项基础面板值为精确匹配（误差 0）。测试使用的角色等级属性是
**合成**夹具值（``base_hp=1000`` 等），不代表任何真实资产数值，且不参与本断言。

不覆盖的行为：暴击判定的随机性与决策器（由 ``CriticalDecisionProvider`` 承担，见
``tests/unit/core/systems/damage/test_damage_system.py`` 对 ``1 + crit_damage`` 的既有
断言）、载体结算的逐帧时序与前后台倍率、资产/内容侧对这三项属性的修饰词条、
面板同步事件的发布时机。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from genshin_sim.application.assembly.attributes import build_attribute_runtime
from genshin_sim.assets.models import CharacterLevelStats
from genshin_sim.core.attributes import (
    GAME_BASE_CHARACTER_PANEL,
    GAME_BASE_CRIT_DAMAGE,
    GAME_BASE_CRIT_RATE,
    GAME_BASE_ENERGY_RECHARGE,
    STAT_CRIT_DAMAGE,
    STAT_CRIT_RATE,
    STAT_ENERGY_RECHARGE,
    AttributeQuery,
    AttributeSubjectRef,
    game_base_panel_source_ref,
)
from genshin_sim.core.systems.energy import InvalidEnergyAttributeError
from genshin_sim.core.systems.energy.formulas import recharge_multiplier
from tests.helpers.assembly import minimal_input


@dataclass(frozen=True, slots=True)
class _AttributeAssetBundle:
    slot: int
    character_level_stats: CharacterLevelStats
    weapon_level_stats: None = None


def _bare_character_runtime():
    """构建一个没有任何资产被动/圣遗物/内容单元的单角色属性运行时。"""

    return build_attribute_runtime(
        config=minimal_input(),
        assets=(
            _AttributeAssetBundle(
                slot=1,
                character_level_stats=CharacterLevelStats(
                    character_key="character:slot_1",
                    level=90,
                    ascension_phase=6,
                    base_hp=1000,
                    base_atk=100,
                    base_def=100,
                    ascension_stat=None,
                    ascension_value=None,
                ),
            ),
        ),
        content_units=(),
    )


def test_game_base_panel_constants_are_the_rule_values():
    assert GAME_BASE_CRIT_RATE == 0.05
    assert GAME_BASE_CRIT_DAMAGE == 0.5
    assert GAME_BASE_ENERGY_RECHARGE == 1.0

    assert GAME_BASE_CHARACTER_PANEL == (
        (STAT_CRIT_RATE, 0.05),
        (STAT_CRIT_DAMAGE, 0.5),
        (STAT_ENERGY_RECHARGE, 1.0),
    )


def test_game_base_panel_source_ref_is_system_scoped():
    source_ref = game_base_panel_source_ref(STAT_CRIT_RATE)

    assert source_ref.kind.value == "system"
    assert source_ref.source_key == "base.stat.crit_rate"


def test_bare_character_gets_the_base_panel_and_target_does_not():
    runtime = _bare_character_runtime()
    character = AttributeSubjectRef.character("character:slot_1")
    target = AttributeSubjectRef.target("target:target_1")

    for key, expected in (
        (STAT_CRIT_RATE, 0.05),
        (STAT_CRIT_DAMAGE, 0.5),
        (STAT_ENERGY_RECHARGE, 1.0),
    ):
        character_resolution = runtime.resolver.resolve(AttributeQuery(character, key, frame=0))
        assert character_resolution.base_value == pytest.approx(expected)
        assert character_resolution.final_value == pytest.approx(expected)

        target_resolution = runtime.resolver.resolve(AttributeQuery(target, key, frame=0))
        assert target_resolution.final_value == 0.0


def test_energy_recharge_multiplier_is_the_absolute_efficiency():
    assert recharge_multiplier(1.0) == pytest.approx(1.0)
    assert recharge_multiplier(1.5) == pytest.approx(1.5)
    assert recharge_multiplier(3.0) == pytest.approx(3.0)


def test_energy_recharge_multiplier_rejects_non_positive_efficiency():
    with pytest.raises(InvalidEnergyAttributeError):
        recharge_multiplier(0.0)
    with pytest.raises(InvalidEnergyAttributeError):
        recharge_multiplier(-0.5)
