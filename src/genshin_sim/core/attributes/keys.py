from __future__ import annotations

import re
from dataclasses import dataclass

from genshin_sim.core.attributes.errors import AttributeValidationError

_ATTRIBUTE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


@dataclass(frozen=True, order=True, slots=True)
class AttributeKey:
    """稳定、可序列化的属性 key。"""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _ATTRIBUTE_KEY_PATTERN.fullmatch(self.value):
            raise AttributeValidationError(f"非法属性 key：{self.value!r}")

    def __str__(self) -> str:
        return self.value


STAT_HP_BASE = AttributeKey("stat.hp.base")
STAT_HP_MAX = AttributeKey("stat.hp.max")
STAT_ATK_BASE = AttributeKey("stat.atk.base")
STAT_ATK_TOTAL = AttributeKey("stat.atk.total")
STAT_DEF_BASE = AttributeKey("stat.def.base")
STAT_DEF_TOTAL = AttributeKey("stat.def.total")

STAT_CRIT_RATE = AttributeKey("stat.crit_rate")
STAT_CRIT_DAMAGE = AttributeKey("stat.crit_damage")
STAT_ELEMENTAL_MASTERY = AttributeKey("stat.elemental_mastery")
STAT_ENERGY_RECHARGE = AttributeKey("stat.energy_recharge")

BONUS_HEALING_OUTGOING = AttributeKey("bonus.healing.outgoing")
BONUS_HEALING_INCOMING = AttributeKey("bonus.healing.incoming")
BONUS_DAMAGE_PHYSICAL = AttributeKey("bonus.damage.physical")
BONUS_DAMAGE_PYRO = AttributeKey("bonus.damage.pyro")
BONUS_DAMAGE_HYDRO = AttributeKey("bonus.damage.hydro")
BONUS_DAMAGE_ELECTRO = AttributeKey("bonus.damage.electro")
BONUS_DAMAGE_CRYO = AttributeKey("bonus.damage.cryo")
BONUS_DAMAGE_ANEMO = AttributeKey("bonus.damage.anemo")
BONUS_DAMAGE_GEO = AttributeKey("bonus.damage.geo")
BONUS_DAMAGE_DENDRO = AttributeKey("bonus.damage.dendro")

RESISTANCE_PHYSICAL = AttributeKey("resistance.physical")
RESISTANCE_PYRO = AttributeKey("resistance.pyro")
RESISTANCE_HYDRO = AttributeKey("resistance.hydro")
RESISTANCE_ELECTRO = AttributeKey("resistance.electro")
RESISTANCE_CRYO = AttributeKey("resistance.cryo")
RESISTANCE_ANEMO = AttributeKey("resistance.anemo")
RESISTANCE_GEO = AttributeKey("resistance.geo")
RESISTANCE_DENDRO = AttributeKey("resistance.dendro")

PUBLIC_ATTRIBUTE_KEYS = (
    STAT_HP_BASE,
    STAT_HP_MAX,
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    STAT_DEF_BASE,
    STAT_DEF_TOTAL,
    STAT_CRIT_RATE,
    STAT_CRIT_DAMAGE,
    STAT_ELEMENTAL_MASTERY,
    STAT_ENERGY_RECHARGE,
    BONUS_HEALING_OUTGOING,
    BONUS_HEALING_INCOMING,
    BONUS_DAMAGE_PHYSICAL,
    BONUS_DAMAGE_PYRO,
    BONUS_DAMAGE_HYDRO,
    BONUS_DAMAGE_ELECTRO,
    BONUS_DAMAGE_CRYO,
    BONUS_DAMAGE_ANEMO,
    BONUS_DAMAGE_GEO,
    BONUS_DAMAGE_DENDRO,
    RESISTANCE_PHYSICAL,
    RESISTANCE_PYRO,
    RESISTANCE_HYDRO,
    RESISTANCE_ELECTRO,
    RESISTANCE_CRYO,
    RESISTANCE_ANEMO,
    RESISTANCE_GEO,
    RESISTANCE_DENDRO,
)

RESISTANCE_KEYS_BY_ELEMENT = {
    "physical": RESISTANCE_PHYSICAL,
    "pyro": RESISTANCE_PYRO,
    "hydro": RESISTANCE_HYDRO,
    "electro": RESISTANCE_ELECTRO,
    "cryo": RESISTANCE_CRYO,
    "anemo": RESISTANCE_ANEMO,
    "geo": RESISTANCE_GEO,
    "dendro": RESISTANCE_DENDRO,
}
BASE_STAT_KEYS = (STAT_HP_BASE, STAT_ATK_BASE, STAT_DEF_BASE)
TOTAL_STAT_KEYS = (STAT_HP_MAX, STAT_ATK_TOTAL, STAT_DEF_TOTAL)
ADDITIVE_STAT_KEYS = tuple(
    key for key in PUBLIC_ATTRIBUTE_KEYS if key not in {*BASE_STAT_KEYS, *TOTAL_STAT_KEYS}
)
ELEMENT_TO_DAMAGE_BONUS_KEY = {
    "physical": BONUS_DAMAGE_PHYSICAL,
    "pyro": BONUS_DAMAGE_PYRO,
    "hydro": BONUS_DAMAGE_HYDRO,
    "electro": BONUS_DAMAGE_ELECTRO,
    "cryo": BONUS_DAMAGE_CRYO,
    "anemo": BONUS_DAMAGE_ANEMO,
    "geo": BONUS_DAMAGE_GEO,
    "dendro": BONUS_DAMAGE_DENDRO,
}
ELEMENT_TO_RESISTANCE_KEY = RESISTANCE_KEYS_BY_ELEMENT


def attribute_key(value: str | AttributeKey) -> AttributeKey:
    if isinstance(value, AttributeKey):
        return value
    return AttributeKey(value)


def is_public_attribute_key(value: str | AttributeKey) -> bool:
    return attribute_key(value) in PUBLIC_ATTRIBUTE_KEYS

