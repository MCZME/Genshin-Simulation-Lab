"""生产 DamageProfile 注册表的反应伤害标签覆盖。

反应伤害标签改为中文后，已注册标签与未注册标签不再由命名空间前缀区分：
未注册标签会静默回落通用公式。本文件把「每个反应伤害标签都注册到期望公式」
固化成回归基线，替代原先由 ``reaction.`` 前缀承担的笔误保护。
"""

from __future__ import annotations

import pytest

from genshin_sim.application.assembly.damage_profiles import (
    create_default_damage_profile_registry,
)
from genshin_sim.core.systems.damage.keys import (
    FORMULA_KEY_LUNAR_REACTION,
    FORMULA_KEY_STELLAR_REACTION,
    FORMULA_KEY_TRANSFORMATIVE_REACTION,
)

TRANSFORMATIVE = FORMULA_KEY_TRANSFORMATIVE_REACTION
LUNAR = FORMULA_KEY_LUNAR_REACTION
STELLAR = FORMULA_KEY_STELLAR_REACTION

REACTION_DAMAGE_TAGS = (
    ("超载伤害", TRANSFORMATIVE),
    ("超导伤害", TRANSFORMATIVE),
    ("碎冰伤害", TRANSFORMATIVE),
    ("感电伤害", TRANSFORMATIVE),
    ("扩散火伤", TRANSFORMATIVE),
    ("扩散水伤", TRANSFORMATIVE),
    ("扩散雷伤", TRANSFORMATIVE),
    ("扩散冰伤", TRANSFORMATIVE),
    ("燃烧伤害", TRANSFORMATIVE),
    ("原绽放伤害", TRANSFORMATIVE),
    ("烈绽放伤害", TRANSFORMATIVE),
    ("超绽放伤害", TRANSFORMATIVE),
    ("月绽放", LUNAR),
    ("月感电", LUNAR),
    ("月结晶", LUNAR),
    ("星超导冰", STELLAR),
    ("星超导雷", STELLAR),
    ("星扩散风", STELLAR),
    ("星扩散冰", STELLAR),
)


@pytest.mark.parametrize(
    ("main_attack_tag", "formula_key"),
    REACTION_DAMAGE_TAGS,
    ids=[tag for tag, _ in REACTION_DAMAGE_TAGS],
)
def test_reaction_damage_tag_resolves_to_expected_formula(
    main_attack_tag: str,
    formula_key: str,
) -> None:
    """每个反应伤害标签都必须显式注册到对应完整公式。"""

    registry = create_default_damage_profile_registry()

    assert registry.resolve_for_main_attack_tag(main_attack_tag).formula_key == formula_key
