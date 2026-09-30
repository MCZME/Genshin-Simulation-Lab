"""桑多涅直伤星烁通道：辉映查表分派与 ``StellarReactionDamageInput`` 组装。

本模块是角色直伤星超导的私有实现（集中放置、不散落），
覆盖冷凝射线/第二枚棱晶弹/聚能光束的 ``星超导冰``/``星扩散冰`` 双分支。
发射或展开时读取辉映状态的属性证据——辉映 Buff 投影到角色属性的
``stellar.conduct.direct_base_multiplier`` / ``stellar.swirl.direct_base_multiplier``
词条——组装 ``StellarReactionDamageInput(mode=character_direct)`` 后随
``DamageImpactSpec.stellar_reaction`` 提交，经 DamageRequestHandler 的星烁
输入通道进入独立星烁公式（星超导反应契约 §8）。组装同时折叠 P6 星烁基础
增伤（每 100 攻击 +0.7%，上限 14%，按实时攻击力折算）与 C6 星烁擢升
（+20%，覆盖星超导与星扩散）。

辉映·星扩散 Buff 的发放目标是星扩散 capability 提供者：桑多涅随内容单元
静态声明该 capability，队伍风命中冰触发星扩散后她持有辉映·星扩散状态，
星扩散冰分支在仿真中可达。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum, auto
from typing import NamedTuple

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_C6_EXTRA_CONDUCT_DISPLAY_NAME,
    SANDRONE_C6_EXTRA_SWIRL_DISPLAY_NAME,
    SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
    SANDRONE_DAMAGE_ELEMENT,
    SANDRONE_ELEMENTAL_BURST_BEAM_AOE_RADIUS,
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_RANGE_TYPE,
    SANDRONE_ELEMENTAL_BURST_STRIKE_TYPE,
    SANDRONE_ELEMENTAL_SKILL_AOE_RADIUS,
    SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_RANGE_TYPE,
    SANDRONE_ELEMENTAL_SKILL_STRIKE_TYPE,
    SANDRONE_P6_BASE_BONUS_CAP,
    SANDRONE_P6_BASE_BONUS_PER_100_ATK,
    SANDRONE_PRISM_STELLAR_ADDITIONAL_TAG,
    SANDRONE_RAY_STELLAR_ADDITIONAL_TAG,
    SANDRONE_STELLAR_BEAM_CONDUCT_LABEL,
    SANDRONE_STELLAR_BEAM_SWIRL_LABEL,
    SANDRONE_STELLAR_PRISM_CONDUCT_LABEL,
    SANDRONE_STELLAR_PRISM_SWIRL_LABEL,
    SANDRONE_STELLAR_RAY_CONDUCT_LABEL,
    SANDRONE_STELLAR_RAY_SWIRL_LABEL,
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
from genshin_sim.core.space import ImpactAreaSpec, Vector3
from genshin_sim.core.systems.damage import DamageScalingTerm
from genshin_sim.core.systems.damage.stellar import StellarReactionDamageInput
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
)


class RadianceVariant(Enum):
    """持用的辉映状态；两者同时成立时星超导优先（D-069）。"""

    CONDUCT = auto()
    SWIRL = auto()


class RadianceEvidence(NamedTuple):
    variant: RadianceVariant
    direct_base_multiplier: float


@dataclass(frozen=True, slots=True)
class SandroneStellarAttackChannel:
    """单类攻击的星烁通道：星超导/星扩散两个变体契约与倍率分量。

    星变体契约不携带普通倍率（直伤倍率由 ``resolve_stellar_attack_spec``
    写入 ``scaling_terms`` 的系数）；
    ``conduct_ratio`` 与 ``swirl_ratio`` 分别取自资产倍率条目的星超导行与
    星扩散行（官方数据直出，组装时不换算）；C6 追加段的两个倍率取自资产命座
    第 6 层效果行。
    ``ascension_bonus`` 为 C6 擢升（覆盖星超导与星扩散，角色自身星烁伤害）。
    """

    impact_key: str
    conduct_spec: DamageImpactSpec
    swirl_spec: DamageImpactSpec
    conduct_ratio: float
    swirl_ratio: float
    ascension_bonus: float = 0.0


@dataclass(frozen=True, slots=True)
class _StellarChannelPlan:
    """星烁通道的命中判定数据行（3.4 星变体行，普通/星扩散行合并表达）。"""

    impact_key: str
    talent_key: str
    conduct_label: str
    swirl_label: str
    strike_type: StrikeType
    range_type: str
    aoe_shape: str | None
    aoe_radius: float
    additional_attack_tags: tuple[str, ...]


_STELLAR_CHANNEL_PLANS = (
    _StellarChannelPlan(
        impact_key=SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
        talent_key="normal_attack",
        conduct_label=SANDRONE_STELLAR_RAY_CONDUCT_LABEL,
        swirl_label=SANDRONE_STELLAR_RAY_SWIRL_LABEL,
        strike_type=StrikeType.BLUNT,
        range_type="远程",
        aoe_shape=None,
        aoe_radius=0.0,
        additional_attack_tags=(SANDRONE_RAY_STELLAR_ADDITIONAL_TAG,),
    ),
    _StellarChannelPlan(
        impact_key=SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY,
        talent_key="elemental_skill",
        conduct_label=SANDRONE_STELLAR_PRISM_CONDUCT_LABEL,
        swirl_label=SANDRONE_STELLAR_PRISM_SWIRL_LABEL,
        strike_type=SANDRONE_ELEMENTAL_SKILL_STRIKE_TYPE,
        range_type=SANDRONE_ELEMENTAL_SKILL_RANGE_TYPE,
        aoe_shape="球",
        aoe_radius=SANDRONE_ELEMENTAL_SKILL_AOE_RADIUS,
        additional_attack_tags=(SANDRONE_PRISM_STELLAR_ADDITIONAL_TAG,),
    ),
    _StellarChannelPlan(
        impact_key=SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
        talent_key="elemental_burst",
        conduct_label=SANDRONE_STELLAR_BEAM_CONDUCT_LABEL,
        swirl_label=SANDRONE_STELLAR_BEAM_SWIRL_LABEL,
        strike_type=SANDRONE_ELEMENTAL_BURST_STRIKE_TYPE,
        range_type=SANDRONE_ELEMENTAL_BURST_RANGE_TYPE,
        aoe_shape="圆柱",
        aoe_radius=SANDRONE_ELEMENTAL_BURST_BEAM_AOE_RADIUS,
        additional_attack_tags=(),
    ),
)


def compile_stellar_attack_channels(
    character_key: str,
    entries_by_key: Mapping[tuple[str, str, str], TalentScalingEntry],
    talent_levels: Mapping[str, int],
    *,
    ascension_bonus: float = 0.0,
) -> dict[str, SandroneStellarAttackChannel]:
    """编译射线/第二枚棱晶弹/光束的星烁通道契约与倍率分量。

    星超导与星扩散倍率各自取同名资产倍率条目，按对应天赋等级取值；两者中
    任一条目或天赋等级缺失时在组装阶段报错，不延迟到仿真运行中。
    ``ascension_bonus`` 传入 C6 擢升，随通道进入全部星烁输入。
    """

    channels: dict[str, SandroneStellarAttackChannel] = {}
    for plan in _STELLAR_CHANNEL_PLANS:
        talent_level = talent_levels.get(plan.talent_key)
        if talent_level is None:
            raise ContentUnitValidationError(f"桑多涅星烁通道缺少天赋等级：{plan.talent_key}")
        conduct_entry = entries_by_key.get((character_key, plan.talent_key, plan.conduct_label))
        swirl_entry = entries_by_key.get((character_key, plan.talent_key, plan.swirl_label))
        if conduct_entry is None:
            raise ContentUnitValidationError(f"桑多涅星超导缺少资产倍率条目：{plan.conduct_label}")
        if swirl_entry is None:
            raise ContentUnitValidationError(f"桑多涅星扩散缺少资产倍率条目：{plan.swirl_label}")
        conduct_compiled = ScalingCompiler.compile_entry(conduct_entry, talent_level)
        swirl_compiled = ScalingCompiler.compile_entry(swirl_entry, talent_level)
        if not conduct_compiled.components:
            raise ContentUnitValidationError(f"桑多涅星超导倍率条目缺少分量：{plan.conduct_label}")
        if not swirl_compiled.components:
            raise ContentUnitValidationError(f"桑多涅星扩散倍率条目缺少分量：{plan.swirl_label}")
        channels[plan.impact_key] = SandroneStellarAttackChannel(
            impact_key=plan.impact_key,
            conduct_spec=_compile_stellar_variant(
                plan,
                talent_level,
                main_attack_tag=STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
                display_name=plan.conduct_label,
            ),
            swirl_spec=_compile_stellar_variant(
                plan,
                talent_level,
                main_attack_tag=STELLAR_SWIRL_ICE_DAMAGE_TAG,
                display_name=plan.swirl_label,
            ),
            conduct_ratio=conduct_compiled.components[0].value,
            swirl_ratio=swirl_compiled.components[0].value,
            ascension_bonus=ascension_bonus,
        )
    return channels


def compile_c6_extra_stellar_channel(
    talent_level: int,
    *,
    conduct_ratio: float,
    swirl_ratio: float,
    ascension_bonus: float,
) -> SandroneStellarAttackChannel:
    """编译 C6 追加段的星烁通道（倍率取资产命座第 6 层效果行）。

    命中判定数据与射线星变体同形（单体/钝击/远程/桑多涅激光标签、0 元素量、
    不参与附着），对应数据表「命之座第6层 集束型冷凝射线星超导 / 星扩散」两行。
    星超导/星扩散倍率与星烁擢升由调用方从资产效果行解析后传入（effects.py
    ``read_c6_asset_values``）——本函数只做契约组装，不留数值常量。
    """

    if conduct_ratio <= 0.0 or swirl_ratio <= 0.0:
        raise ContentUnitValidationError("C6 追加段星烁倍率必须为正数")
    if ascension_bonus < 0.0:
        raise ContentUnitValidationError("C6 星烁擢升不能为负数")
    ray_plan = _STELLAR_CHANNEL_PLANS[0]
    if ray_plan.impact_key != SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY:
        raise ContentUnitValidationError("C6 追加段星烁通道缺少射线命中判定计划")
    return SandroneStellarAttackChannel(
        impact_key=SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
        conduct_spec=_compile_stellar_variant(
            ray_plan,
            talent_level,
            main_attack_tag=STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
            display_name=SANDRONE_C6_EXTRA_CONDUCT_DISPLAY_NAME,
        ),
        swirl_spec=_compile_stellar_variant(
            ray_plan,
            talent_level,
            main_attack_tag=STELLAR_SWIRL_ICE_DAMAGE_TAG,
            display_name=SANDRONE_C6_EXTRA_SWIRL_DISPLAY_NAME,
        ),
        conduct_ratio=conduct_ratio,
        swirl_ratio=swirl_ratio,
        ascension_bonus=ascension_bonus,
    )


def stellar_base_bonus_for_atk(atk: float) -> float:
    """P6 星烁基础增伤：每 100 点攻击力 +0.7%，至多 14%（线性折算）。"""

    return min(atk / 100.0 * SANDRONE_P6_BASE_BONUS_PER_100_ATK, SANDRONE_P6_BASE_BONUS_CAP)


def resolve_stellar_attack_spec(
    channel: SandroneStellarAttackChannel,
    *,
    simulation: SimulationContext | None,
    owner_ref: str,
    frame: int,
    extra_multiplier: float = 0.0,
) -> DamageImpactSpec | None:
    """辉映状态查表分派：返回星变体契约（附星烁输入），无辉映时返回 None。

    证据为辉映 Buff 投影到 ``owner_ref`` 的直伤系数词条：值 > 0 视为持用
    对应辉映状态，星超导优先（D-069）。倍率与属性分开承载（D-082）：变体
    倍率分量（与 ``extra_multiplier`` 按倍率区相加）写进 ``scaling_terms``
    的系数，属性固定为攻击力、由公式侧从面板读取，不再预乘成缩放值。星烁
    输入随组装折叠 P6 星烁基础增伤（按攻击力折算）与通道携带的 C6 擢升。
    缺少仿真上下文或属性解析器时保守回落普通通道。
    """

    evidence = radiance_evidence(simulation, owner_ref, frame)
    if evidence is None or simulation is None:
        return None
    if evidence.variant is RadianceVariant.CONDUCT:
        base_spec, ratio = channel.conduct_spec, channel.conduct_ratio
    else:
        base_spec, ratio = channel.swirl_spec, channel.swirl_ratio
    atk = resolve_attribute_final_value(simulation, owner_ref, STAT_ATK_TOTAL, frame)
    return replace(
        base_spec,
        scaling_terms=(
            DamageScalingTerm(
                component_key=channel.impact_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=ratio + extra_multiplier,
            ),
        ),
        stellar_reaction=StellarReactionDamageInput(
            mode="character_direct",
            stellar_base_multiplier=evidence.direct_base_multiplier,
            stellar_base_bonus=stellar_base_bonus_for_atk(atk),
            stellar_ascension_bonus=channel.ascension_bonus,
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
    resolver = simulation.get_system(AttributeResolver)
    if not isinstance(resolver, AttributeResolver):
        return None
    conduct = resolve_attribute_final_value(
        simulation, owner_ref, STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER, frame
    )
    if conduct > 0.0:
        return RadianceEvidence(RadianceVariant.CONDUCT, conduct)
    swirl = resolve_attribute_final_value(
        simulation, owner_ref, STELLAR_SWIRL_DIRECT_BASE_MULTIPLIER, frame
    )
    if swirl > 0.0:
        return RadianceEvidence(RadianceVariant.SWIRL, swirl)
    return None


def resolve_attribute_final_value(
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


def _compile_stellar_variant(
    plan: _StellarChannelPlan,
    talent_level: int,
    *,
    main_attack_tag: str,
    display_name: str,
) -> DamageImpactSpec:
    """编译单个星变体契约：无普通倍率、不附着、无 ICD（星烁请求边界）。"""

    return DamageImpactSpec(
        impact_ref=f"{plan.impact_key}:{talent_level}",
        main_attack_tag=main_attack_tag,
        element=SANDRONE_DAMAGE_ELEMENT,
        scaling_terms=(),
        can_crit=True,
        additional_attack_tags=plan.additional_attack_tags,
        strike_type=plan.strike_type,
        range_type=plan.range_type,
        elemental_amount=AuraAmount.zero(),
        display_name=display_name,
        area=(
            ImpactAreaSpec(
                shape=plan.aoe_shape,
                radius=plan.aoe_radius,
                local_offset_xz=Vector3(),
            )
            if plan.aoe_shape is not None
            else None
        ),
    )
