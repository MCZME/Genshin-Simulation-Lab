"""元素共鸣内容定义：稳定 key、激活条件与静态数值。"""

from __future__ import annotations

from fractions import Fraction

from genshin_sim.core.attributes import (
    BONUS_SHIELD_STRENGTH,
    RESISTANCE_GEO,
    RESISTANCE_KEYS_BY_ELEMENT,
    STAT_ATK_TOTAL,
    STAT_ELEMENTAL_MASTERY,
    STAT_HP_MAX,
    AttributeSubjectKind,
    ModifierStage,
)
from genshin_sim.core.elements import AuraKind, Element
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffStackScaling,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.reaction.mechanics.bloom.keys import (
    BLOOM_REACTION_KEY,
    BURGEON_REACTION_KEY,
    HYPERBLOOM_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.burning.mechanic import (
    BURNING_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.catalyze.mechanic import (
    AGGRAVATE_REACTION_KEY,
    QUICKEN_REACTION_KEY,
    SPREAD_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.electro_charged.mechanic import (
    ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom.keys import (
    LUNAR_BLOOM_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.overloaded.mechanic import (
    OVERLOADED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.superconduct.mechanic import (
    SUPERCONDUCT_REACTION_KEY,
)
from genshin_sim.core.systems.resonance import (
    ResonanceAuraDurationRule,
    ResonanceDefinition,
    ResonanceRequirement,
    ResonanceStaticModifier,
)

RESONANCE_PYRO = "resonance.pyro"
RESONANCE_HYDRO = "resonance.hydro"
RESONANCE_ANEMO = "resonance.anemo"
RESONANCE_ELECTRO = "resonance.electro"
RESONANCE_CRYO = "resonance.cryo"
RESONANCE_GEO = "resonance.geo"
RESONANCE_DENDRO = "resonance.dendro"
RESONANCE_INTERWOVEN = "resonance.intertwined"

RESONANCE_KEYS = (
    RESONANCE_PYRO,
    RESONANCE_HYDRO,
    RESONANCE_ANEMO,
    RESONANCE_ELECTRO,
    RESONANCE_CRYO,
    RESONANCE_GEO,
    RESONANCE_DENDRO,
    RESONANCE_INTERWOVEN,
)

RESONANCE_DENDRO_EM_30_BUFF_KEY = "buff.definition:resonance.dendro.em_30"
RESONANCE_DENDRO_EM_20_BUFF_KEY = "buff.definition:resonance.dendro.em_20"
RESONANCE_GEO_RES_SHRED_BUFF_KEY = "buff.definition:resonance.geo.res_shred"

ELECTRO_PARTICLE_TRIGGER_KEYS = frozenset(
    {
        SUPERCONDUCT_REACTION_KEY,
        OVERLOADED_REACTION_KEY,
        ELECTRO_CHARGED_REACTION_KEY,
        LUNAR_ELECTRO_CHARGED_REACTION_KEY,
        QUICKEN_REACTION_KEY,
        AGGRAVATE_REACTION_KEY,
        HYPERBLOOM_REACTION_KEY,
    }
)

DENDRO_EM_30_TRIGGER_KEYS = frozenset(
    {
        BURNING_REACTION_KEY,
        QUICKEN_REACTION_KEY,
        BLOOM_REACTION_KEY,
        LUNAR_BLOOM_REACTION_KEY,
    }
)

DENDRO_EM_20_TRIGGER_KEYS = frozenset(
    {
        AGGRAVATE_REACTION_KEY,
        SPREAD_REACTION_KEY,
        HYPERBLOOM_REACTION_KEY,
        BURGEON_REACTION_KEY,
    }
)


def create_resonance_definitions() -> tuple[ResonanceDefinition, ...]:
    """返回当前内容支持的共鸣定义。

    数值基线：原神 BWIKI《队伍加成》页，2026-07-02 更新（覆盖月之八版本）。
    双雷不包含尚未实现的星超导；双风体力/移速与四系附着时长缩短属于
    后续切片，不在静态定义中。
    """

    return (
        ResonanceDefinition(
            RESONANCE_PYRO,
            ResonanceRequirement.element_count(Element.PYRO),
            (
                ResonanceStaticModifier(
                    STAT_ATK_TOTAL,
                    ModifierStage.PERCENT_ADD,
                    0.25,
                    ("atk_percent",),
                ),
            ),
            aura_duration_rules=(ResonanceAuraDurationRule(AuraKind.CRYO, Fraction(3, 5)),),
        ),
        ResonanceDefinition(
            RESONANCE_HYDRO,
            ResonanceRequirement.element_count(Element.HYDRO),
            (
                ResonanceStaticModifier(
                    STAT_HP_MAX,
                    ModifierStage.PERCENT_ADD,
                    0.25,
                    ("hp_percent",),
                ),
            ),
            aura_duration_rules=(ResonanceAuraDurationRule(AuraKind.PYRO, Fraction(3, 5)),),
        ),
        ResonanceDefinition(
            RESONANCE_ANEMO,
            ResonanceRequirement.element_count(Element.ANEMO),
            cooldown_duration_multiplier=Fraction(95, 100),
        ),
        ResonanceDefinition(
            RESONANCE_ELECTRO,
            ResonanceRequirement.element_count(Element.ELECTRO),
            aura_duration_rules=(ResonanceAuraDurationRule(AuraKind.HYDRO, Fraction(3, 5)),),
        ),
        ResonanceDefinition(
            RESONANCE_CRYO,
            ResonanceRequirement.element_count(Element.CRYO),
            aura_duration_rules=(ResonanceAuraDurationRule(AuraKind.ELECTRO, Fraction(3, 5)),),
        ),
        ResonanceDefinition(
            RESONANCE_GEO,
            ResonanceRequirement.element_count(Element.GEO),
            (
                ResonanceStaticModifier(
                    BONUS_SHIELD_STRENGTH,
                    ModifierStage.FLAT_ADD,
                    0.15,
                    ("shield_strength",),
                ),
            ),
        ),
        ResonanceDefinition(
            RESONANCE_DENDRO,
            ResonanceRequirement.element_count(Element.DENDRO),
            (
                ResonanceStaticModifier(
                    STAT_ELEMENTAL_MASTERY,
                    ModifierStage.FLAT_ADD,
                    50.0,
                    ("elemental_mastery",),
                ),
            ),
        ),
        ResonanceDefinition(
            RESONANCE_INTERWOVEN,
            ResonanceRequirement.distinct_elements(4),
            tuple(
                ResonanceStaticModifier(
                    target_key,
                    ModifierStage.FLAT_ADD,
                    0.15,
                    ("resistance",),
                )
                for target_key in RESISTANCE_KEYS_BY_ELEMENT.values()
            ),
        ),
    )


def create_resonance_buff_definitions() -> tuple[BuffDefinition, ...]:
    """双草反应触发的全队精通与双岩命中减抗 Buff 定义。"""

    em_template = BuffAttributeModifierTemplate(
        term_key="elemental_mastery",
        target_key=STAT_ELEMENTAL_MASTERY,
        stage=ModifierStage.FLAT_ADD,
        stack_scaling=BuffStackScaling.CONSTANT,
        audit_tags=("resonance.dendro",),
    )
    res_shred_template = BuffAttributeModifierTemplate(
        term_key="resistance_geo",
        target_key=RESISTANCE_GEO,
        stage=ModifierStage.FLAT_ADD,
        stack_scaling=BuffStackScaling.CONSTANT,
        audit_tags=("resonance.geo",),
    )
    return (
        BuffDefinition(
            definition_key=RESONANCE_DENDRO_EM_30_BUFF_KEY,
            mechanic_key="resonance.dendro.em_30",
            handler_key="resonance.dendro",
            conflict_key="resonance.dendro.em_30",
            target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
            application_policy=BuffApplicationPolicy.REFRESH,
            value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
            max_stacks=1,
            attribute_modifiers=(em_template,),
            tags=frozenset({"resonance.dendro", "em_30"}),
        ),
        BuffDefinition(
            definition_key=RESONANCE_DENDRO_EM_20_BUFF_KEY,
            mechanic_key="resonance.dendro.em_20",
            handler_key="resonance.dendro",
            conflict_key="resonance.dendro.em_20",
            target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
            application_policy=BuffApplicationPolicy.REFRESH,
            value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
            max_stacks=1,
            attribute_modifiers=(em_template,),
            tags=frozenset({"resonance.dendro", "em_20"}),
        ),
        BuffDefinition(
            definition_key=RESONANCE_GEO_RES_SHRED_BUFF_KEY,
            mechanic_key="resonance.geo.res_shred",
            handler_key="resonance.geo",
            conflict_key="resonance.geo.res_shred",
            target_kinds=frozenset({AttributeSubjectKind.TARGET}),
            application_policy=BuffApplicationPolicy.REFRESH,
            value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
            max_stacks=1,
            attribute_modifiers=(res_shred_template,),
            tags=frozenset({"resonance.geo", "res_shred"}),
        ),
    )
