"""月兆（挪德卡徕地区效果）golden 基线。

验证能力：月兆等级判定与非月兆角色月曜增伤公式（含 36% 上限与 20 秒时长）。
资料来源及适用版本：原神 BWIKI《队伍加成》页「月兆」节（2026-07-02 更新，
覆盖月之八版本）。
旧项目参考：`moonsign_system.py` 与非月兆增益测试（数值一致）。
完整输入条件：见各用例内联数据。
预期输出与允许误差：公式值使用精确小数断言（1e-9）。
不覆盖的行为：月兆角色专属初辉/满辉强化（依赖具体角色 content）、新月之拥。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.team.moonsign import (
    MOONSIGN_BONUS_CAP,
    MOONSIGN_BONUS_DURATION_FRAMES,
    MOONSIGN_SCALING_BY_ELEMENT,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.moonsign import (
    MoonsignLevel,
    MoonsignStatSnapshot,
    resolve_moonsign_level,
    resolve_non_moonsign_bonus,
)


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, MoonsignLevel.NONE), (1, MoonsignLevel.NASCENT), (2, MoonsignLevel.ASCENDANT)],
    ids=("none", "nascent", "ascendant"),
)
def test_moonsign_level_from_character_count(count: int, expected: MoonsignLevel):
    assert resolve_moonsign_level(count) is expected


@pytest.mark.parametrize(
    ("element", "stats", "expected"),
    [
        (Element.PYRO, MoonsignStatSnapshot(2000, 0, 0, 0), 0.18),
        (Element.ELECTRO, MoonsignStatSnapshot(2000, 0, 0, 0), 0.18),
        (Element.CRYO, MoonsignStatSnapshot(2000, 0, 0, 0), 0.18),
        (Element.HYDRO, MoonsignStatSnapshot(0, 30000, 0, 0), 0.18),
        (Element.GEO, MoonsignStatSnapshot(0, 0, 2000, 0), 0.2),
        (Element.ANEMO, MoonsignStatSnapshot(0, 0, 0, 800), 0.18),
        (Element.DENDRO, MoonsignStatSnapshot(0, 0, 0, 1000), 0.225),
        (Element.PYRO, MoonsignStatSnapshot(4000, 0, 0, 0), 0.36),
        (Element.HYDRO, MoonsignStatSnapshot(0, 60000, 0, 0), 0.36),
        (Element.GEO, MoonsignStatSnapshot(0, 0, 3600, 0), 0.36),
        (Element.ANEMO, MoonsignStatSnapshot(0, 0, 0, 1600), 0.36),
    ],
    ids=(
        "pyro_atk_0.18",
        "electro_atk_0.18",
        "cryo_atk_0.18",
        "hydro_hp_0.18",
        "geo_def_0.20",
        "anemo_em_0.18",
        "dendro_em_0.225",
        "pyro_atk_cap_0.36",
        "hydro_hp_cap_0.36",
        "geo_def_cap_0.36",
        "anemo_em_cap_0.36",
    ),
)
def test_non_moonsign_lunar_bonus_golden(element, stats, expected):
    value = resolve_non_moonsign_bonus(
        element,
        stats,
        MOONSIGN_SCALING_BY_ELEMENT,
        MOONSIGN_BONUS_CAP,
    )
    assert value == pytest.approx(expected, rel=0.0, abs=1e-9)


def test_non_moonsign_bonus_duration_is_1200_frames():
    assert MOONSIGN_BONUS_DURATION_FRAMES == 1200
