"""翡玉法球内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:14304``）。
被动「激流」：触发蒸发、感电、冰冻、绽放、月感电、月绽放或水元素扩散后的
12 秒内，攻击力提升。
"""

from __future__ import annotations

from genshin_sim.core.systems.reaction.mechanics.bloom.keys import BLOOM_REACTION_KEY
from genshin_sim.core.systems.reaction.mechanics.electro_charged.mechanic import (
    ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.frozen.keys import FROZEN_REACTION_KEY
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom.keys import (
    LUNAR_BLOOM_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.swirl.mechanic import (
    HYDRO_SWIRL,
    SWIRL_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.vaporize.mechanic import (
    VAPORIZE_REACTION_KEY,
)

EMERALD_ORB_KEY_PREFIX = "weapon.emerald_orb"
EMERALD_ORB_HANDLER_KEY = EMERALD_ORB_KEY_PREFIX
EMERALD_ORB_PASSIVE_EFFECT_HANDLER_KEY = f"{EMERALD_ORB_KEY_PREFIX}.passive"
EMERALD_ORB_CONTENT_VERSION = "dev-emerald-orb"

# 攻击力 Buff「激流」的属性词条键。
EMERALD_ORB_ATK_TERM_KEY = f"{EMERALD_ORB_KEY_PREFIX}.atk_percent"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案）：攻击力提升持续 12 秒。
BUFF_DURATION_SECONDS = 12.0

# 触发面：文案列举的反应键 + 水元素扩散方向键。键值取自各反应机制的定义，
# 本内容包只做集合声明，不复制字面量。
TRIGGER_REACTION_KEYS = frozenset(
    {
        VAPORIZE_REACTION_KEY,
        ELECTRO_CHARGED_REACTION_KEY,
        FROZEN_REACTION_KEY,
        BLOOM_REACTION_KEY,
        LUNAR_ELECTRO_CHARGED_REACTION_KEY,
        LUNAR_BLOOM_REACTION_KEY,
    }
)
SWIRL_REACTION_KEY_DECLARED = SWIRL_REACTION_KEY
SWIRL_DIRECTION_KEYS = frozenset({HYDRO_SWIRL})

# 资产效果参数的位置约定：components[0] 是攻击力提升。
ATK_PERCENT_COMPONENT_INDEX = 0
