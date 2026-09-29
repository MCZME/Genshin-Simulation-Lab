"""星烁反应独立伤害公式的结构与纯计算。

本模块只承载星烁公式的**反应身份、结构与机制侧冻结基线**，以及
"槽位合并值 → 伤害"的纯计算。影响数值的效果一律以 ``DamageModifierTerm``
进入槽位账单，由 ``core/systems/damage/formulas.py`` 的结算分支收集、署名与消费；
倍率与属性由请求的 ``scaling_terms`` 承载，不再由本模块承载预乘结果。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from genshin_sim.core.attributes import AttributeSubjectKind, AttributeSubjectRef

# 反应星烁复合模式按折前伤害稳定排序后保留的参与者上限。
STELLAR_COMPOSITE_PARTICIPANT_LIMIT = 4

# 星烁公式的槽位键：与 allowed_modifier_stages 白名单按位置一一对应，
# 供槽位三段审计（冻结基线 / Σ修饰项 / 合并值）稳定命名。
STELLAR_SLOT_BASE_MULTIPLIER = "stellar_base_multiplier"
STELLAR_SLOT_BASE_BONUS = "stellar_base_bonus"
STELLAR_SLOT_REACTION_BONUS = "stellar_reaction_bonus"
STELLAR_SLOT_AUTHORITY_MULTIPLIER = "stellar_authority_multiplier"
STELLAR_SLOT_FEATHER_ADDITION = "stellar_feather_addition"
STELLAR_SLOT_ASCENSION_BONUS = "stellar_ascension_bonus"


@dataclass(frozen=True, slots=True)
class StellarZoneSlotAudit:
    """星烁一个可修饰位置的三段审计。

    ``baseline`` 是机制侧冻结或面板读取得到的基础值，``modifier_sum`` 是从槽位
    账单收集到的修饰项合计，``merged`` 是进入公式实算的合并值。三段同时保留，
    使 ``merged`` 偏离基线时可以定位到是谁贡献了多少。
    """

    slot_key: str
    baseline: float
    modifier_sum: float
    merged: float

    def __post_init__(self) -> None:
        for name in ("baseline", "modifier_sum", "merged"):
            object.__setattr__(
                self,
                name,
                validate_slot_float(getattr(self, name), f"{self.slot_key}.{name}"),
            )

    def to_dict(self) -> dict[str, object]:
        """返回稳定的槽位审计字典。"""

        return {
            "slot_key": self.slot_key,
            "baseline": self.baseline,
            "modifier_sum": self.modifier_sum,
            "merged": self.merged,
        }


def validate_slot_float(value: float, name: str) -> float:
    """校验槽位审计数值是有限数字。"""

    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} 必须是有限数字")
    return normalized


@dataclass(frozen=True, slots=True)
class StellarZoneDamage:
    """星烁十位置公式的一次纯计算结果。

    ``base_damage`` 是括号值（倍率区 × 基础系数 × 基础增伤 × 精通增伤区 × 大权区
    + 羽毛区），``damage`` 是在此之上乘算暴击、抗性与擢升后的总伤害。分开保留
    是为了让扁平结果模型能用括号值填 ``base_damage``，与月曜同构。
    """

    base_damage: float
    critical_multiplier: float
    resistance_multiplier: float
    ascension_multiplier: float
    damage: float

    def __post_init__(self) -> None:
        for name in (
            "base_damage",
            "critical_multiplier",
            "resistance_multiplier",
            "ascension_multiplier",
            "damage",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"星烁 {name} 必须是有限非负数")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, object]:
        """返回稳定的区间计算结果字典。"""

        return {
            "base_damage": self.base_damage,
            "critical_multiplier": self.critical_multiplier,
            "resistance_multiplier": self.resistance_multiplier,
            "ascension_multiplier": self.ascension_multiplier,
            "damage": self.damage,
        }


@dataclass(frozen=True, slots=True)
class StellarReactionParticipantInput:
    """星烁复合伤害中一名参与者的 Damage 侧输入。

    ``reaction_base_value`` 是该参与者自身等级对应的星烁反应基础值（观察期
    冻结），作为该组分的倍率区基线；星烁基础增伤、星烁增伤、星烁大权区、
    反应星烁羽毛区与星烁擢升按参与者各自携带；元素精通、暴击与目标抗性由
    公式实时读取。所有可修饰位置的效果一律通过槽位账单进入，不写入本结构。
    """

    participant_ref: AttributeSubjectRef
    source_level: int
    reaction_base_value: float
    stellar_base_bonus: float = 0.0
    stellar_bonus: float = 0.0
    stellar_authority_multiplier: float = 1.0
    stellar_feather_addition: float = 0.0
    stellar_ascension_bonus: float = 0.0
    can_crit: bool = True

    def __post_init__(self) -> None:
        if self.participant_ref.kind is not AttributeSubjectKind.CHARACTER:
            raise ValueError("星烁伤害参与者必须是角色主体")
        if (
            isinstance(self.source_level, bool)
            or not isinstance(self.source_level, int)
            or self.source_level <= 0
        ):
            raise ValueError("星烁伤害参与者等级必须是正整数")
        for name in (
            "reaction_base_value",
            "stellar_base_bonus",
            "stellar_bonus",
            "stellar_authority_multiplier",
            "stellar_feather_addition",
            "stellar_ascension_bonus",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} 必须是有限数字")
            object.__setattr__(self, name, value)
        if self.reaction_base_value < 0 or self.stellar_feather_addition < 0:
            raise ValueError("星烁参与者基础值和羽毛区不能为负数")
        if self.stellar_authority_multiplier < 0 or self.stellar_ascension_bonus < 0:
            raise ValueError("星烁参与者乘数不能为负数")
        if not isinstance(self.can_crit, bool):
            raise ValueError("星烁参与者 can_crit 必须是布尔值")


@dataclass(frozen=True, slots=True)
class StellarReactionDamageInput:
    """星烁伤害的结构与机制侧冻结基线。

    只承载反应身份、来源模式与机制侧冻结的基线值；倍率与属性由请求的
    ``scaling_terms`` 承载。内容效果不得在此预乘或预换算，否则数值与署名
    会同时脱离槽位账单。
    """

    mode: str
    stellar_base_multiplier: float
    stellar_base_bonus: float = 0.0
    stellar_bonus: float = 0.0
    stellar_authority_multiplier: float = 1.0
    direct_stellar_feather_addition: float = 0.0
    stellar_ascension_bonus: float = 0.0
    participants: tuple[StellarReactionParticipantInput, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in {"character_direct", "reaction_composite"}:
            raise ValueError("星烁伤害 mode 不受支持")
        for name in (
            "stellar_base_multiplier",
            "stellar_base_bonus",
            "stellar_bonus",
            "stellar_authority_multiplier",
            "direct_stellar_feather_addition",
            "stellar_ascension_bonus",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} 必须是有限数字")
            object.__setattr__(self, name, value)
        if self.stellar_base_multiplier < 0:
            raise ValueError("星烁基础系数不能为负数")
        if self.direct_stellar_feather_addition < 0:
            raise ValueError("星烁羽毛区不能为负数")
        if self.stellar_authority_multiplier < 0:
            raise ValueError("星烁大权区乘数不能为负数")
        participants = tuple(self.participants)
        if any(not isinstance(item, StellarReactionParticipantInput) for item in participants):
            raise ValueError("participants 必须是 StellarReactionParticipantInput 序列")
        participant_ids = [item.participant_ref.entity_id for item in participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("星烁伤害参与者不能重复角色")
        if self.mode == "character_direct" and participants:
            raise ValueError("角色直伤星烁不能携带参与者列表")
        object.__setattr__(
            self,
            "participants",
            tuple(sorted(participants, key=lambda item: item.participant_ref.entity_id)),
        )


@dataclass(frozen=True, slots=True)
class StellarReactionComponentResolution:
    """反应星烁复合模式中一名参与者的独立结算审计。"""

    participant_ref: AttributeSubjectRef
    source_level: int
    reaction_base_value: float
    elemental_mastery: float
    mastery_bonus: float
    critical: Any | None
    resistance: Any | None
    component_damage: float
    weight: float
    weighted_damage: float
    # 该组分的括号值（暴击/抗性/擢升之前），供顶层扁平结果按权重聚合。
    base_damage: float = 0.0
    # 该组分独立收集到的伤害修饰项。复合路径的修饰不进入顶层 applied_terms，
    # 因此在此单独保留，使数值与审计重新对齐。
    modifier_terms: tuple[Any, ...] = ()
    # 该组分从属性系统读取到的面板值物化成的词条（精通、暴击、抗性），
    # 与 modifier_terms 合成该组分的槽位账单。
    panel_terms: tuple[Any, ...] = ()
    # 该组分各可修饰位置的三段审计；倍率区基线是该参与者的反应基础值。
    slots: tuple[StellarZoneSlotAudit, ...] = ()
    source_attribute_trace: tuple[Any, ...] = ()
    target_attribute_trace: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "reaction_base_value",
            "elemental_mastery",
            "mastery_bonus",
            "component_damage",
            "base_damage",
            "weight",
            "weighted_damage",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} 必须是有限非负数")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "modifier_terms", tuple(self.modifier_terms))
        object.__setattr__(self, "panel_terms", tuple(self.panel_terms))
        slots = tuple(self.slots)
        if any(not isinstance(item, StellarZoneSlotAudit) for item in slots):
            raise ValueError("slots 必须是 StellarZoneSlotAudit 序列")
        object.__setattr__(self, "slots", slots)

    def to_dict(self) -> dict[str, object]:
        return {
            "participant_ref": {
                "kind": self.participant_ref.kind.value,
                "entity_id": self.participant_ref.entity_id,
            },
            "source_level": self.source_level,
            "reaction_base_value": self.reaction_base_value,
            "elemental_mastery": self.elemental_mastery,
            "mastery_bonus": self.mastery_bonus,
            "crit_outcome": (None if self.critical is None else self.critical.outcome.value),
            "crit_multiplier": (None if self.critical is None else self.critical.multiplier),
            "resistance_multiplier": (
                None if self.resistance is None else self.resistance.multiplier
            ),
            "component_damage": self.component_damage,
            "base_damage": self.base_damage,
            "weight": self.weight,
            "weighted_damage": self.weighted_damage,
            "slots": [item.to_dict() for item in self.slots],
            "modifier_terms": [item.to_dict() for item in self.modifier_terms],
            "panel_terms": [item.to_dict() for item in self.panel_terms],
        }


@dataclass(frozen=True, slots=True)
class StellarReactionDamageResolution:
    """星烁伤害的公式输入与区间审计。

    纯计算只填充 ``input``、``base_damage`` 与 ``damage``；结算器分支额外写入
    实时元素精通、暴击区、抗性区、槽位三段审计与面板词条。``reaction_composite``
    模式以 ``components`` 承载逐参与者结算与权重聚合，顶层字段取排名第一
    参与者的实时读取投影。审计对象由 damage 模块构造，本模块不引入对
    ``models`` 的运行时依赖。
    """

    input: StellarReactionDamageInput
    damage: float
    base_damage: float = 0.0
    elemental_mastery: float = 0.0
    mastery_bonus: float = 0.0
    critical: Any | None = None
    resistance: Any | None = None
    official_damage: float = 0.0
    debug_multiplier: float = 1.0
    final_damage: float = 0.0
    components: tuple[StellarReactionComponentResolution, ...] = field(default=())
    # 各可修饰位置的槽位三段审计；复合模式在组分内各自保留。
    slots: tuple[StellarZoneSlotAudit, ...] = field(default=())
    # 公式从属性系统读取到的面板值物化成的词条，与 applied_terms 合成槽位账单。
    panel_terms: tuple[Any, ...] = field(default=())
    # 直伤模式的倍率区结果（组件贡献、固定加值与区合计）。
    scaling: Any | None = None
    source_attribute_trace: tuple[Any, ...] = field(default=())
    target_attribute_trace: tuple[Any, ...] = field(default=())

    def __post_init__(self) -> None:
        for name in (
            "damage",
            "base_damage",
            "elemental_mastery",
            "mastery_bonus",
            "official_damage",
            "debug_multiplier",
            "final_damage",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} 必须是有限非负数")
            object.__setattr__(self, name, value)
        components = tuple(self.components)
        if any(not isinstance(item, StellarReactionComponentResolution) for item in components):
            raise ValueError("components 必须是 StellarReactionComponentResolution 序列")
        object.__setattr__(self, "components", components)
        slots = tuple(self.slots)
        if any(not isinstance(item, StellarZoneSlotAudit) for item in slots):
            raise ValueError("slots 必须是 StellarZoneSlotAudit 序列")
        object.__setattr__(self, "slots", slots)

    def merged_slot(self, slot_key: str, fallback: float) -> float:
        """返回指定槽位的合并值；没有该槽位审计时回退到冻结基线。"""

        for item in self.slots:
            if item.slot_key == slot_key:
                return item.merged
        return fallback

    def to_dict(self) -> dict[str, object]:
        """返回稳定的星烁伤害审计摘要。

        ``stellar_*`` 键取该槽位的**合并值**，与实算使用的一致；各槽位的冻结
        基线与修饰项合计在 ``slots`` 中完整保留。
        """

        payload: dict[str, object] = {
            "mode": self.input.mode,
            "base_damage": self.base_damage,
            "stellar_base_multiplier": self.merged_slot(
                STELLAR_SLOT_BASE_MULTIPLIER, self.input.stellar_base_multiplier
            ),
            "stellar_base_bonus": self.merged_slot(
                STELLAR_SLOT_BASE_BONUS, self.input.stellar_base_bonus
            ),
            "elemental_mastery": self.elemental_mastery,
            "mastery_bonus": self.mastery_bonus,
            "stellar_bonus": self.merged_slot(
                STELLAR_SLOT_REACTION_BONUS, self.input.stellar_bonus
            ),
            "stellar_authority_multiplier": self.merged_slot(
                STELLAR_SLOT_AUTHORITY_MULTIPLIER, self.input.stellar_authority_multiplier
            ),
            "direct_stellar_feather_addition": self.merged_slot(
                STELLAR_SLOT_FEATHER_ADDITION, self.input.direct_stellar_feather_addition
            ),
            "crit_outcome": (None if self.critical is None else self.critical.outcome.value),
            "crit_rate": (None if self.critical is None else self.critical.crit_rate),
            "crit_damage": (None if self.critical is None else self.critical.crit_damage),
            "crit_multiplier": (None if self.critical is None else self.critical.multiplier),
            "resistance_multiplier": (
                None if self.resistance is None else self.resistance.multiplier
            ),
            "base_resistance": (
                None if self.resistance is None else self.resistance.base_resistance
            ),
            "resistance_add": (None if self.resistance is None else self.resistance.resistance_add),
            "stellar_ascension_bonus": self.merged_slot(
                STELLAR_SLOT_ASCENSION_BONUS, self.input.stellar_ascension_bonus
            ),
            "official_damage": self.official_damage,
            "debug_multiplier": self.debug_multiplier,
            "final_damage": self.final_damage,
        }
        if self.slots:
            payload["slots"] = [item.to_dict() for item in self.slots]
        if self.components:
            payload["components"] = [item.to_dict() for item in self.components]
        return payload


def resolve_stellar_zone_damage(
    *,
    scaling_zone_damage: float,
    stellar_base_multiplier: float,
    elemental_mastery: float,
    stellar_base_bonus: float,
    stellar_bonus: float,
    stellar_authority_multiplier: float,
    feather_addition: float,
    critical_multiplier: float,
    resistance_multiplier: float,
    stellar_ascension_bonus: float,
) -> StellarZoneDamage:
    """按资料中的星烁区间顺序结算一名参与者的十位置公式。

    入参全部是**已合并的槽位值**（冻结基线 + 槽位账单修饰项合计），本函数不做
    任何收集或署名：那是结算分支的职责。``scaling_zone_damage`` 是倍率区合并值
    （属性 × 系数），由倍率区策略给出。
    """

    mastery = 6.0 * elemental_mastery / (elemental_mastery + 2000.0)
    base_damage = (
        scaling_zone_damage
        * stellar_base_multiplier
        * (1.0 + stellar_base_bonus)
        * (1.0 + mastery + stellar_bonus)
        * stellar_authority_multiplier
        + feather_addition
    )
    ascension_multiplier = 1.0 + stellar_ascension_bonus
    damage = base_damage * critical_multiplier * resistance_multiplier * ascension_multiplier
    if not math.isfinite(damage) or damage < 0:
        raise ValueError("星烁伤害结果必须是有限非负数")
    return StellarZoneDamage(
        base_damage=base_damage,
        critical_multiplier=critical_multiplier,
        resistance_multiplier=resistance_multiplier,
        ascension_multiplier=ascension_multiplier,
        damage=damage,
    )
