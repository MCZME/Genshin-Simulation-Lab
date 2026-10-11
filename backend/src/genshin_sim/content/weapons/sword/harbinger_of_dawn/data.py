"""黎明神剑内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:11302``）。
被动「激励」：生命值高于 90% 时，暴击率提升（按精炼取值）。

落点说明：暴击率是面板属性，因此走 Buff 属性词条（``stat.crit_rate`` 平铺加成），
条件期间由 ``FRAME_STARTED`` tick 周期性续期维持。
"""

from __future__ import annotations

HARBINGER_OF_DAWN_KEY_PREFIX = "weapon.harbinger_of_dawn"
HARBINGER_OF_DAWN_HANDLER_KEY = HARBINGER_OF_DAWN_KEY_PREFIX
HARBINGER_OF_DAWN_PASSIVE_EFFECT_HANDLER_KEY = f"{HARBINGER_OF_DAWN_KEY_PREFIX}.passive"
HARBINGER_OF_DAWN_CONTENT_VERSION = "dev-harbinger-of-dawn"

# 暴击率 Buff 的词条键。
HARBINGER_OF_DAWN_CRIT_RATE_TERM_KEY = f"{HARBINGER_OF_DAWN_KEY_PREFIX}.crit_rate"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 条件重评与 Buff 续期口径（工程约定，见 hp_gated_buff 模块说明）：
# 每 10 帧（1/6 秒）重评一次条件，Buff 每次施加持续 20 帧（1/3 秒）。
# 游戏内条件失效时加成立即消失；本实现的残留窗口不作为游戏真值。
HP_GATE_REFRESH_INTERVAL_FRAMES = 10
CRIT_RATE_BUFF_DURATION_FRAMES = 20

# 生命阈值：高于 90%。资产效果参数不含阈值，由本内容包按文案声明。
HP_THRESHOLD = 0.9

# 资产效果参数的位置约定：components[0] 是暴击率提升。
CRIT_RATE_COMPONENT_INDEX = 0
