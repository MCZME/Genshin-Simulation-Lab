"""DamageProfile 注册表唯一装配入口。

runtime 装配阶段只消费本模块产出的注册表，不直接内联构造
``DamageProfile``。内容侧 profile 由各自内容包声明，反应侧 profile
由各自 mechanic 模块声明，本模块只做汇总。测试探针 profile
（``runtime_probe`` / ``damage_probe``）暂以字面量注册在本入口，避免
注册入口依赖尚未纳入仓库的 ``content/test`` 内容；待测试内容随仓库提交后，
再迁移到对应测试内容包的 ``profiles.py``。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara.profiles import (
    barbara_damage_profiles,
)
from genshin_sim.core.systems.damage import DamageProfile, DamageProfileRegistry, DamageType
from genshin_sim.core.systems.reaction.mechanics.bloom import bloom_damage_profiles
from genshin_sim.core.systems.reaction.mechanics.burning import burning_damage_profile
from genshin_sim.core.systems.reaction.mechanics.catalyze import catalyze_damage_profile
from genshin_sim.core.systems.reaction.mechanics.electro_charged import (
    electro_charged_damage_profile,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom import (
    lunar_bloom_damage_profiles,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize import (
    lunar_crystallize_damage_profiles,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged import (
    lunar_electro_charged_damage_profiles,
)
from genshin_sim.core.systems.reaction.mechanics.overloaded import (
    overloaded_damage_profile,
)
from genshin_sim.core.systems.reaction.mechanics.shattered import (
    shattered_damage_profile,
)
from genshin_sim.core.systems.reaction.mechanics.superconduct import (
    superconduct_damage_profile,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import swirl_damage_profile


def create_default_damage_profile_registry() -> DamageProfileRegistry:
    """组装当前生产全部 DamageProfile 的默认注册表。"""

    return DamageProfileRegistry(
        (
            *barbara_damage_profiles(),
            DamageProfile(
                "damage_profile.testing.runtime_probe",
                DamageType.GENERAL,
                frozenset({"testing.runtime_probe.direct"}),
            ),
            DamageProfile(
                "damage_profile.testing.damage_probe",
                DamageType.GENERAL,
                frozenset({"testing.damage_probe.direct"}),
            ),
            overloaded_damage_profile(),
            superconduct_damage_profile(),
            shattered_damage_profile(),
            electro_charged_damage_profile(),
            swirl_damage_profile(),
            burning_damage_profile(),
            catalyze_damage_profile(),
            *bloom_damage_profiles(),
            *lunar_bloom_damage_profiles(),
            *lunar_electro_charged_damage_profiles(),
            *lunar_crystallize_damage_profiles(),
        )
    )
