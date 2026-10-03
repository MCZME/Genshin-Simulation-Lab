"""奥黛塔直伤星烁通道：辉映查表分派与星变体契约编译。

本模块是奥黛塔直伤星烁的私有实现（包内同构，不跨角色包 import），覆盖
破晓终奏结束段与拂羽/旋翼舞步的「星超导冰/星扩散冰」双分支。两者辉映
门控口径不同（资产技能文本定案）：结束段基础文本无条件「视为星超导反应
伤害」，辉映只改变持用的变体与基础系数，无辉映证据时按星超导变体、系数
1 出伤；舞步星变体文本以「奥黛塔处于辉映·星烁状态」为前提，无辉映证据
时不出伤（C1 追加段口径与结束段一致）。

发射时读取辉映状态的属性证据——辉映 Buff 投影到角色属性的
``stellar.conduct.direct_base_multiplier`` / ``stellar.swirl.direct_base_multiplier``
词条——组装 ``StellarReactionDamageInput(mode=character_direct)`` 后随
``DamageImpactSpec.stellar_reaction`` 提交，经 DamageRequestHandler 的星烁
输入通道进入独立星烁公式（星超导反应契约 §8）。星烁输入只携带机制侧冻结
基线（辉映基础系数）；P6 星烁基础增伤由伤害修饰 provider 在结算期产出词条
（见 ``modifiers.py``），不在组装期折叠。

奥黛塔的星超导/星扩散倍率在资产倍率表中是同一「星超导/星扩散伤害」条目的
两个分量（分量 0 = 星超导、分量 1 = 星扩散），与桑多涅的独立条目不同。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum, auto
from typing import NamedTuple

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_DAMAGE_ELEMENT,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.generic.talents import ScalingCompiler
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER,
    STELLAR_SWIRL_DIRECT_BASE_MULTIPLIER,
    AttributeKey,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectRef,
)
from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.impacts import DamageImpactSpec, StrikeType
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.space import ImpactAreaSpec
from genshin_sim.core.systems.damage import DamageScalingTerm
from genshin_sim.core.systems.damage.stellar import StellarReactionDamageInput
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
    STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
    STELLAR_SWIRL_WIND_DAMAGE_TAG,
)

# 星烁反应伤害标签（星超导冰/雷、星扩散冰/风），含携带对应标签的星变体直伤
# 与反应本体伤害。华彩「星烁反应伤害」增伤与擢升的覆盖口径按此集合理解
# （sandrone C1/P6 同款口径）。
STELLAR_REACTION_DAMAGE_TAGS = frozenset(
    {
        STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
        STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG,
        STELLAR_SWIRL_ICE_DAMAGE_TAG,
        STELLAR_SWIRL_WIND_DAMAGE_TAG,
    }
)


class RadianceVariant(Enum):
    """持用的辉映状态；两者同时成立时星超导优先（D-069）。"""

    CONDUCT = auto()
    SWIRL = auto()


class RadianceEvidence(NamedTuple):
    variant: RadianceVariant
    direct_base_multiplier: float


@dataclass(frozen=True, slots=True)
class OdetteStellarChannel:
    """单类攻击的星烁通道：星超导/星扩散两个变体契约与倍率分量。

    星变体契约不携带普通倍率（直伤倍率由 ``resolve_stellar_variant_spec``
    写入 ``scaling_terms`` 的系数）；``conduct_ratio`` 与 ``swirl_ratio``
    取自资产倍率条目「星超导/星扩散伤害」条目的两个分量。P6 星烁基础增伤
    不进通道：由伤害修饰 provider 在结算期产出词条（D-082）。
    """

    impact_key: str
    conduct_spec: DamageImpactSpec
    swirl_spec: DamageImpactSpec
    conduct_ratio: float
    swirl_ratio: float


def compile_stellar_channel(
    impact_key: str,
    *,
    character_key: str,
    entries_by_key: Mapping[tuple[str, str, str], TalentScalingEntry],
    talent_key: str,
    label: str,
    talent_level: int,
    conduct_spec: DamageImpactSpec,
    swirl_spec: DamageImpactSpec,
) -> OdetteStellarChannel:
    """按「星超导/星扩散伤害」双分量倍率条目编译星烁通道。

    星变体契约（几何/标签/元素量）由调用方按命中数据表行给出，本函数只从
    资产倍率条目取两个分量并填充通道；条目缺失或分量不足在组装阶段报错。
    """

    entry = entries_by_key.get((character_key, talent_key, label))
    if entry is None:
        raise ContentUnitValidationError(f"奥黛塔缺少资产倍率条目：{label}")
    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    if len(compiled.components) < 2:
        raise ContentUnitValidationError(f"奥黛塔倍率条目缺少星超导/星扩散双分量：{label}")
    return OdetteStellarChannel(
        impact_key=impact_key,
        conduct_spec=conduct_spec,
        swirl_spec=swirl_spec,
        conduct_ratio=compiled.components[0].value,
        swirl_ratio=compiled.components[1].value,
    )


def resolve_stellar_variant_spec(
    channel: OdetteStellarChannel,
    *,
    simulation: SimulationContext | None,
    owner_ref: str,
    frame: int,
    conduct_fallback: bool = False,
) -> DamageImpactSpec | None:
    """辉映状态查表分派：返回星变体契约（附星烁输入），无辉映时返回 None。

    证据为辉映 Buff 投影到 ``owner_ref`` 的直伤系数词条：值 > 0 视为持用
    对应辉映状态，星超导优先。倍率与属性分开承载：变体倍率分量写进
    ``scaling_terms`` 的系数，属性固定为攻击力、由公式侧从面板读取。

    ``conduct_fallback`` 承载结束段口径：无辉映证据时按星超导变体、星烁
    基础系数 1 出伤（与辉映 0 层同值，对齐星超导反应设计 §6「0 层时基础
    系数为 1」）；舞步星变体的辉映门控不传该参数。
    """

    evidence = radiance_evidence(simulation, owner_ref, frame)
    if evidence is None:
        if not conduct_fallback or simulation is None:
            return None
        evidence = RadianceEvidence(RadianceVariant.CONDUCT, 1.0)
    if evidence.variant is RadianceVariant.CONDUCT:
        base_spec, ratio = channel.conduct_spec, channel.conduct_ratio
    else:
        base_spec, ratio = channel.swirl_spec, channel.swirl_ratio
    return replace(
        base_spec,
        scaling_terms=(
            DamageScalingTerm(
                component_key=channel.impact_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=ratio,
            ),
        ),
        stellar_reaction=StellarReactionDamageInput(
            mode="character_direct",
            stellar_base_multiplier=evidence.direct_base_multiplier,
        ),
    )


def radiance_evidence(
    simulation: SimulationContext | None,
    owner_ref: str,
    frame: int,
) -> RadianceEvidence | None:
    """读取 ``owner_ref`` 当前的辉映属性证据；无辉映时返回 None。"""

    if simulation is None:
        return None
    conduct = _resolve_final_value(
        simulation, owner_ref, STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER, frame
    )
    if conduct > 0.0:
        return RadianceEvidence(RadianceVariant.CONDUCT, conduct)
    swirl = _resolve_final_value(simulation, owner_ref, STELLAR_SWIRL_DIRECT_BASE_MULTIPLIER, frame)
    if swirl > 0.0:
        return RadianceEvidence(RadianceVariant.SWIRL, swirl)
    return None


def _resolve_final_value(
    simulation: SimulationContext,
    owner_ref: str,
    attribute_key: AttributeKey,
    frame: int,
) -> float:
    resolver = simulation.get_system(AttributeResolver)
    if not isinstance(resolver, AttributeResolver):
        raise ContentUnitValidationError("缺少 AttributeResolver，无法读取辉映属性证据")
    resolution = resolver.resolve(
        AttributeQuery(
            subject_ref=AttributeSubjectRef.character(owner_ref),
            attribute_key=attribute_key,
            frame=frame,
        )
    )
    return float(resolution.final_value)


def stellar_variant_hit(
    *,
    impact_ref: str,
    main_attack_tag: str,
    display_name: str,
    strike_type: StrikeType,
    range_type: str,
    area: ImpactAreaSpec | None,
) -> DamageImpactSpec:
    """编译单个星变体契约：无普通倍率、不附着、无 ICD（星烁请求边界）。

    几何/打击类型/远近类型取自命中数据表星变体行，由调用方按行构造传入；
    ``area=None`` 表示单体（命中集合由调用方的索敌确定）。``impact_ref``
    只作契约占位标识，随请求改写。
    """

    return DamageImpactSpec(
        impact_ref=impact_ref,
        main_attack_tag=main_attack_tag,
        element=ODETTE_DAMAGE_ELEMENT,
        scaling_terms=(),
        can_crit=True,
        strike_type=strike_type,
        range_type=range_type,
        elemental_amount=AuraAmount.zero(),
        display_name=display_name,
        area=area,
    )
