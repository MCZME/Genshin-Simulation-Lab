"""芭芭拉内容包 Damage Profile 注册定义。"""

from __future__ import annotations

from genshin_sim.core.systems.damage import DamageProfile, DamageType


def barbara_damage_profiles() -> tuple[DamageProfile, ...]:
    """芭芭拉角色直伤使用的稳定 Damage Profile。"""

    return (
        DamageProfile(
            "damage_profile.character.barbara",
            DamageType.GENERAL,
            frozenset(
                {
                    "普通攻击1",
                    "普通攻击2",
                    "普通攻击3",
                    "普通攻击4",
                    "重击",
                    "元素战技",
                    "下落攻击",
                }
            ),
        ),
    )
