"""暗铁剑内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:11304``）。
被动「过载」：触发超载、超导、星超导、感电、原激化、超激化、超绽放、月感电
或雷元素扩散反应后的 12 秒内，攻击力提升。
"""

from __future__ import annotations

from genshin_sim.core.systems.reaction.mechanics.bloom.keys import HYPERBLOOM_REACTION_KEY
from genshin_sim.core.systems.reaction.mechanics.catalyze.mechanic import (
    AGGRAVATE_REACTION_KEY,
    QUICKEN_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.electro_charged.mechanic import (
    ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.overloaded.mechanic import (
    OVERLOADED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.superconduct.mechanic import (
    SUPERCONDUCT_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.swirl.mechanic import (
    ELECTRO_SWIRL,
    SWIRL_REACTION_KEY,
)

DARK_IRON_SWORD_KEY_PREFIX = "weapon.dark_iron_sword"
DARK_IRON_SWORD_HANDLER_KEY = DARK_IRON_SWORD_KEY_PREFIX
DARK_IRON_SWORD_PASSIVE_EFFECT_HANDLER_KEY = f"{DARK_IRON_SWORD_KEY_PREFIX}.passive"
DARK_IRON_SWORD_CONTENT_VERSION = "dev-dark-iron-sword"

# 攻击力 Buff「过载」的属性词条键。
DARK_IRON_SWORD_ATK_TERM_KEY = f"{DARK_IRON_SWORD_KEY_PREFIX}.atk_percent"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案）：攻击力提升持续 12 秒。
BUFF_DURATION_SECONDS = 12.0

# 触发面：文案列举的反应键 + 雷元素扩散方向键。键值取自各反应机制的定义，
# 本内容包只做集合声明，不复制字面量。
TRIGGER_REACTION_KEYS = frozenset(
    {
        OVERLOADED_REACTION_KEY,
        SUPERCONDUCT_REACTION_KEY,
        STELLAR_CONDUCT_REACTION_KEY,
        ELECTRO_CHARGED_REACTION_KEY,
        QUICKEN_REACTION_KEY,
        AGGRAVATE_REACTION_KEY,
        HYPERBLOOM_REACTION_KEY,
        LUNAR_ELECTRO_CHARGED_REACTION_KEY,
    }
)
SWIRL_REACTION_KEY_DECLARED = SWIRL_REACTION_KEY
SWIRL_DIRECTION_KEYS = frozenset({ELECTRO_SWIRL})

# 资产效果参数的位置约定：components[0] 是攻击力提升。
ATK_PERCENT_COMPONENT_INDEX = 0
