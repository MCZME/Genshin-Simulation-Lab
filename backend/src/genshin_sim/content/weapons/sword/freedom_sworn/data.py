"""苍古自由之誓内容数据"""

from __future__ import annotations

FREEDOM_SWORN_KEY_PREFIX = "weapon.freedom_sworn"
FREEDOM_SWORN_HANDLER_KEY = FREEDOM_SWORN_KEY_PREFIX
FREEDOM_SWORN_PASSIVE_EFFECT_HANDLER_KEY = f"{FREEDOM_SWORN_KEY_PREFIX}.passive"
FREEDOM_SWORN_CONTENT_VERSION = "release"

# 「千年的大乐章·抗争之歌」的属性词条键。
FREEDOM_SWORN_SONG_ATK_TERM_KEY = f"{FREEDOM_SWORN_KEY_PREFIX}.song_atk_percent"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案，不是我们维护的词汇表）：
# - 造成的伤害提高（常驻段）；
# - 触发元素反应时获得一枚奋起之符，每 0.5 秒内至多触发一次，
#   角色处于队伍后台也能触发；
# - 拥有 2 枚奋起之符时消耗所有奋起之符，使附近的队伍中所有角色获得持续
#   12 秒的「千年的大乐章·抗争之歌」；
# - 触发后 20 秒内，无法再次获得奋起之符。
SIGIL_TRIGGER_INTERVAL_SECONDS = 0.5
SONG_DURATION_SECONDS = 12.0
SIGIL_LOCKOUT_SECONDS = 20.0
SIGILS_REQUIRED = 2

# 普通攻击/重击/下落攻击伤害的主攻击标签判定：普通攻击标签带段数后缀
# （普通攻击1、普通攻击2、……），需前缀匹配；重击与下落攻击无后缀。
NORMAL_ATTACK_TAG_PREFIX = "普通攻击"
CHARGED_ATTACK_TAG = "重击"
PLUNGING_ATTACK_TAG = "下落攻击"

# 资产效果参数的位置约定：
# components[0] 造成的伤害提高、components[1] 普/重/落伤害提高、
# components[2] 攻击力提升。
DAMAGE_BONUS_COMPONENT_INDEX = 0
SONG_ATTACK_TAG_DAMAGE_COMPONENT_INDEX = 1
SONG_ATK_COMPONENT_INDEX = 2
REQUIRED_COMPONENT_COUNT = 3


def is_normal_charged_plunging_tag(tag: str) -> bool:
    """判定主攻击标签是否属于普通攻击、重击或下落攻击。"""

    return tag in (CHARGED_ATTACK_TAG, PLUNGING_ATTACK_TAG) or tag.startswith(
        NORMAL_ATTACK_TAG_PREFIX
    )
