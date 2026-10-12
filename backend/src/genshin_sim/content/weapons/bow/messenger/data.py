"""信使内容数据：稳定键与版本。

范围边界：「重击若命中要害则额外造成攻击力伤害（必定暴击，每 10 秒只能
触发一次）」依赖命中部位判定与额外伤害链路，仿真不建模弱点（D-095），本包
被动按 no-op 处理并在此记录；接入部位判定后重写本包。
"""

from __future__ import annotations

MESSENGER_KEY_PREFIX = "weapon.messenger"
MESSENGER_HANDLER_KEY = MESSENGER_KEY_PREFIX
MESSENGER_PASSIVE_EFFECT_HANDLER_KEY = f"{MESSENGER_KEY_PREFIX}.passive"
MESSENGER_CONTENT_VERSION = "dev-messenger"
