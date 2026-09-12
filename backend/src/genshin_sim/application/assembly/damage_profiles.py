"""DamageProfile 注册表唯一装配入口。

runtime 装配阶段只消费本模块产出的注册表，不直接内联构造
``DamageProfile``。注册表只保存非通用公式的显式映射（剧变、月曜）；
未注册的非反应标签由注册表默认解析为通用公式，``reaction.`` 前缀标签
未注册时在装配或运行时明确报错。
"""

from __future__ import annotations

from genshin_sim.core.systems.damage import (
    FORMULA_KEY_STELLAR_REACTION,
    DamageProfileRegistry,
)
from genshin_sim.core.systems.damage.models import DamageProfile
from genshin_sim.core.systems.reaction.mechanics.bloom import bloom_damage_profiles
from genshin_sim.core.systems.reaction.mechanics.burning import burning_damage_profile
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
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct import (
    STELLAR_CONDUCT_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.superconduct import (
    superconduct_damage_profile,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import swirl_damage_profile


def stellar_reaction_damage_profile() -> DamageProfile:
    """星烁直伤主攻击标签到独立星烁公式的稳定映射。

    这不是反应侧的普通 Reaction Damage Profile：星超导不注册 Damage kind
    或 Damage Gate，此映射只承担主攻击标签到 ``damage_formula.stellar_reaction``
    的公式选择。
    """

    return DamageProfile(
        FORMULA_KEY_STELLAR_REACTION,
        frozenset({STELLAR_CONDUCT_REACTION_KEY}),
    )


def create_default_damage_profile_registry() -> DamageProfileRegistry:
    """组装当前生产全部非通用 DamageProfile 的默认注册表。"""

    return DamageProfileRegistry(
        (
            overloaded_damage_profile(),
            superconduct_damage_profile(),
            shattered_damage_profile(),
            electro_charged_damage_profile(),
            swirl_damage_profile(),
            burning_damage_profile(),
            *bloom_damage_profiles(),
            *lunar_bloom_damage_profiles(),
            *lunar_electro_charged_damage_profiles(),
            *lunar_crystallize_damage_profiles(),
            stellar_reaction_damage_profile(),
        )
    )
