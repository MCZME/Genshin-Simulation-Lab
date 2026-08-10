"""元素共鸣静态效果 golden 基线。

验证能力：队伍满员时的共鸣激活判定与静态属性数值。
资料来源及适用版本：原神 BWIKI《队伍加成》页（2026-07-02 更新，覆盖月之八版本；
双草/双岩在 6.0/6.4 的适配已包含；双雷暂不包含星超导，本仓库未实现该反应）。
旧项目参考：`resonance_system.py` 的静态注入数值与新资料一致。
完整输入条件：4 人队伍元素构成如下；角色 base_hp=10000、base_atk=1000、base_def=700，
无武器与圣遗物静态贡献。
预期输出与允许误差：属性解析最终值精确匹配（浮点使用 pytest.approx）。
不覆盖的行为：双雷/双冰/双风/双草反应触发、双岩命中减抗、四系附着时长修正。
"""

from __future__ import annotations

import pytest

from genshin_sim.application.assembly.attributes import build_attribute_runtime
from genshin_sim.application.assembly.resonance import build_resonance_bundle
from genshin_sim.core.attributes import (
    BONUS_SHIELD_STRENGTH,
    RESISTANCE_CRYO,
    RESISTANCE_ELECTRO,
    RESISTANCE_PYRO,
    STAT_ATK_TOTAL,
    STAT_ELEMENTAL_MASTERY,
    STAT_HP_MAX,
    AttributeQuery,
    AttributeSubjectRef,
)
from tests.helpers.assembly import minimal_config
from tests.helpers.team_assets import make_team_asset_bundles


@pytest.mark.parametrize(
    ("elements", "expected_keys", "expected"),
    [
        (
            ("pyro", "pyro", "hydro", "hydro"),
            ("resonance.hydro", "resonance.pyro"),
            {
                STAT_ATK_TOTAL: 1250.0,
                STAT_HP_MAX: 12500.0,
                BONUS_SHIELD_STRENGTH: 0.0,
            },
        ),
        (
            ("pyro", "hydro", "electro", "cryo"),
            ("resonance.intertwined",),
            {
                STAT_ATK_TOTAL: 1000.0,
                RESISTANCE_PYRO: 0.15,
                RESISTANCE_ELECTRO: 0.15,
                RESISTANCE_CRYO: 0.15,
            },
        ),
        (
            ("pyro", "pyro", "dendro", "dendro"),
            ("resonance.dendro", "resonance.pyro"),
            {
                STAT_ATK_TOTAL: 1250.0,
                STAT_ELEMENTAL_MASTERY: 50.0,
                BONUS_SHIELD_STRENGTH: 0.0,
            },
        ),
        (
            ("geo", "geo", "hydro", "hydro"),
            ("resonance.geo", "resonance.hydro"),
            {
                STAT_ATK_TOTAL: 1000.0,
                STAT_HP_MAX: 12500.0,
                BONUS_SHIELD_STRENGTH: 0.15,
            },
        ),
    ],
    ids=(
        "pyro_pyro_hydro_hydro",
        "pyro_hydro_electro_cryo",
        "pyro_pyro_dendro_dendro",
        "geo_geo_hydro_hydro",
    ),
)
def test_elemental_resonance_static_golden(
    elements: tuple[str, ...],
    expected_keys: tuple[str, ...],
    expected: dict,
):
    assets = make_team_asset_bundles(elements)
    bundle = build_resonance_bundle(assets)
    runtime = build_attribute_runtime(
        config=minimal_config(),
        assets=assets,
        content_units=(),
        extra_providers=bundle.static_providers,
    )

    assert bundle.activation.active_keys == expected_keys
    subject = AttributeSubjectRef.character("character:slot_1")
    for key, value in expected.items():
        resolution = runtime.resolver.resolve(AttributeQuery(subject, key, 0))
        assert resolution.final_value == pytest.approx(value, rel=0.0, abs=1e-9)
