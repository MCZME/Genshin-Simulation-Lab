"""桑多涅 C6 集束型追加段的契约层单元测试（合成资产数据，见测试规范 §3.2）。

C6 官方文本：解算模式下第三次发射冷凝射线起，在原本射线上追加集束型冷凝
射线伤害，至多 4 段（普通 100% 攻击力；辉映下转为对应星烁反应伤害，星超导
80% / 星扩散 120%）。本文件锁定三件事：

1. 追加段取数据表「命之座第6层 集束型冷凝射线」行的附加标签与命中判定数据；
2. 射线本身的附加标签不被替换（「桑多涅重击普通激光」仍在，追加段另带
   6 命标签）；
3. 追加段星烁通道的标签与倍率分量（星超导/星扩散行）。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_C6_EXTRA_ADDITIONAL_TAG,
    SANDRONE_C6_EXTRA_CONDUCT_DISPLAY_NAME,
    SANDRONE_C6_EXTRA_DISPLAY_NAME,
    SANDRONE_C6_EXTRA_SWIRL_DISPLAY_NAME,
    SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
    SANDRONE_RAY_ADDITIONAL_TAG,
    SANDRONE_RAY_ICD_TAG_KEY,
    SANDRONE_RAY_STELLAR_ADDITIONAL_TAG,
)
from genshin_sim.content.characters.snezhnaya.sandrone.impacts import (
    compile_c6_extra_normal_spec,
    compile_charged_attack_damage_specs,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    compile_c6_extra_stellar_channel,
)
from genshin_sim.content.generic.talents import index_talent_scalings
from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
)
from tests.helpers import sandrone as sandrone_helpers

TALENT_LEVEL = 1


def _ray_spec():
    entries = index_talent_scalings(
        sandrone_helpers.SANDRONE_CHARACTER_KEY,
        sandrone_helpers._minimal_sandrone_scaling_entries(),
    )
    specs = compile_charged_attack_damage_specs(
        sandrone_helpers.SANDRONE_CHARACTER_KEY,
        entries,
        TALENT_LEVEL,
    )
    return specs[SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY]


def test_ray_spec_keeps_its_own_additional_tag() -> None:
    # 射线契约不因 C6 改写：附加标签仍是数据表「重击 冷凝射线」行的
    # 桑多涅重击普通激光（6 命标签只属于追加段那一行）。
    spec = _ray_spec()
    assert spec.additional_attack_tags == (SANDRONE_RAY_ADDITIONAL_TAG,)
    assert SANDRONE_C6_EXTRA_ADDITIONAL_TAG not in spec.additional_attack_tags


def test_extra_normal_spec_matches_hit_data_row() -> None:
    # 数据表「命之座第6层 集束型冷凝射线」行：攻击标签 重击、附加标签
    # 桑多涅重击普通激光6命、钝击、远程、附加标签 重击射线、1 元素量、单体。
    spec = compile_c6_extra_normal_spec()
    assert spec.main_attack_tag == "重击"
    assert spec.additional_attack_tags == (SANDRONE_C6_EXTRA_ADDITIONAL_TAG,)
    assert spec.strike_type is StrikeType.BLUNT
    assert spec.range_type == "远程"
    assert spec.icd_tag_key == SANDRONE_RAY_ICD_TAG_KEY
    assert spec.elemental_amount == AuraAmount.one()
    assert spec.area is None
    assert spec.display_name == SANDRONE_C6_EXTRA_DISPLAY_NAME
    # 倍率固定 100% 攻击力（C6 无资产倍率条目）。
    assert len(spec.scaling_terms) == 1
    assert spec.scaling_terms[0].coefficient == 1.0


def test_extra_stellar_channel_matches_stellar_hit_data_rows() -> None:
    # 数据表「命之座第6层 集束型冷凝射线星超导 / 星扩散」两行：攻击标签
    # 星超导冰/星扩散冰、附加标签 桑多涅激光、钝击、远程、0 元素量、无 ICD。
    channel = compile_c6_extra_stellar_channel(TALENT_LEVEL)
    conduct = channel.conduct_spec
    swirl = channel.swirl_spec
    assert conduct.main_attack_tag == STELLAR_CONDUCT_CRYO_DAMAGE_TAG
    assert swirl.main_attack_tag == STELLAR_SWIRL_ICE_DAMAGE_TAG
    for spec in (conduct, swirl):
        assert spec.additional_attack_tags == (SANDRONE_RAY_STELLAR_ADDITIONAL_TAG,)
        assert spec.strike_type is StrikeType.BLUNT
        assert spec.range_type == "远程"
        assert spec.elemental_amount == AuraAmount.zero()
        assert spec.scaling_terms == ()
    assert conduct.display_name == SANDRONE_C6_EXTRA_CONDUCT_DISPLAY_NAME
    assert swirl.display_name == SANDRONE_C6_EXTRA_SWIRL_DISPLAY_NAME
    # 倍率分量取 C6 官方描述值（星超导 80% / 星扩散 120%），擢升 +20%。
    assert channel.conduct_ratio == 0.8
    assert channel.swirl_ratio == 1.2
    assert channel.ascension_bonus == 0.2
