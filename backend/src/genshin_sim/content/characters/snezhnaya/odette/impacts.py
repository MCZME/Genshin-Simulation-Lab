"""奥黛塔影响契约编译与影响点展开。

本文件负责“资产数据 -> 伤害契约 -> ImpactRequest”的链路：命中几何、打击
类型、衰减序列/衰减标签与附加标签取自 ``data.py`` 的命中数据，倍率来自资产
倍率表（普攻/重击/下落走 normal_attack，战技走 elemental_skill，爆发走
elemental_burst）。破晓终奏持续段为普通动作影响点；结束段与舞步的星变体
经 ``stellar.py`` 星烁通道在展开时按辉映证据分派；独舞倒影创建影响点展开为
CREATE_ENTITY 请求（召唤物本体与轮换见 ``dance.py``）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_BURST_FINAL_HIT,
    ODETTE_BURST_SLASH_1_HIT,
    ODETTE_BURST_SLASH_2_HIT,
    ODETTE_BURST_SLASH_3_HIT,
    ODETTE_C1_EXTRA_IMPACT_KEY,
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_CHARGED_ATTACK_HIT,
    ODETTE_CHARGED_ATTACK_IMPACT_KEY,
    ODETTE_DAMAGE_ELEMENT,
    ODETTE_DAMAGE_ELEMENTAL_AMOUNT,
    ODETTE_DAMAGE_ELEMENTAL_STRENGTH,
    ODETTE_DANCE_DURATION_FRAMES,
    ODETTE_DANCE_OBJECT_KEY,
    ODETTE_DANCE_PLUME_HIT,
    ODETTE_DANCE_PLUME_IMPACT_KEY,
    ODETTE_DANCE_RESUME_AFTER_SPECIAL_FRAMES,
    ODETTE_DANCE_SEARCH_RADIUS,
    ODETTE_DANCE_STEP_PLUME,
    ODETTE_DANCE_STEP_WING,
    ODETTE_DANCE_WING_HIT,
    ODETTE_DANCE_WING_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_FINAL_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_SLASH_1_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_SLASH_2_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_SLASH_3_IMPACT_KEY,
    ODETTE_ELEMENTAL_SKILL_ACTION_KEY,
    ODETTE_ELEMENTAL_SKILL_HIT,
    ODETTE_ELEMENTAL_SKILL_IMPACT_KEY,
    ODETTE_MELEE_ELEMENT,
    ODETTE_NORMAL_ATTACK_DAMAGE_PLANS,
    ODETTE_PLUNGE_ATTACK_DATA,
    ODETTE_PLUNGE_COLLISION_IMPACT_KEY,
    ODETTE_PLUNGE_LANDING_IMPACT_KEY,
    ODETTE_SPECIAL_DOT_1_IMPACT_KEY,
    ODETTE_SPECIAL_DOT_2_IMPACT_KEY,
    ODETTE_SPECIAL_DOT_3_IMPACT_KEY,
    ODETTE_SPECIAL_DOT_HIT,
    ODETTE_SPECIAL_END_IMPACT_KEY,
    ODETTE_SPECIAL_RESUME_IMPACT_FRAME,
    ODETTE_SPECIAL_RESUME_IMPACT_KEY,
    ODETTE_SUMMON_CREATE_IMPACT_KEY,
    OdetteHitData,
)
from genshin_sim.content.characters.snezhnaya.odette.dream import (
    SwanDreamGrantConfig,
    swan_dream_grant_request,
)
from genshin_sim.content.characters.snezhnaya.odette.splendor import (
    OdetteSplendorError,
    SplendorGrantConfig,
    summon_grant_requests,
)
from genshin_sim.content.characters.snezhnaya.odette.stellar import (
    OdetteStellarChannel,
    compile_stellar_channel,
    resolve_stellar_variant_spec,
    stellar_variant_hit,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.generic.talents import ScalingCompiler
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.impacts import (
    ActionImpactContext,
    DamageImpactSpec,
    ImpactKind,
    ImpactRequest,
    StrikeType,
)
from genshin_sim.core.space import ImpactAreaSpec, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID
from genshin_sim.core.systems.damage import DamageScalingTerm
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
)

if TYPE_CHECKING:
    pass


def _compile_damage_spec(
    impact_key: str,
    talent_level: int,
    *,
    entry: TalentScalingEntry,
    component_index: int,
    hit_data: OdetteHitData,
    element_by_amount: bool = True,
    display_name: str,
) -> DamageImpactSpec:
    """把单个资产倍率分量与命中数据行编译为伤害契约。

    ``element_by_amount`` 为 ``False`` 时强制物理/零元素量（普攻与重击未获
    转化时为物理，命中数据表的元素量仅在攻击具元素时生效）。
    """

    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    if len(compiled.components) <= component_index:
        raise ContentUnitValidationError(
            f"奥黛塔倍率条目缺少第 {component_index + 1} 个分量：{display_name}"
        )
    component = compiled.components[component_index]
    if element_by_amount:
        element = ODETTE_DAMAGE_ELEMENT
        elemental_amount = ODETTE_DAMAGE_ELEMENTAL_AMOUNT
        elemental_strength = ODETTE_DAMAGE_ELEMENTAL_STRENGTH
    else:
        element = ODETTE_MELEE_ELEMENT
        elemental_amount = AuraAmount.zero()
        elemental_strength = None
    return DamageImpactSpec(
        impact_ref=f"{impact_key}:{talent_level}",
        main_attack_tag=hit_data.main_attack_tag,
        element=element,
        scaling_terms=(
            DamageScalingTerm(
                component_key=component.component_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=component.value,
            ),
        ),
        can_crit=True,
        additional_attack_tags=hit_data.additional_attack_tags,
        strike_type=hit_data.strike_type,
        range_type=hit_data.range_type,
        elemental_strength=elemental_strength,
        elemental_amount=elemental_amount,
        icd_tag_key=hit_data.icd_tag_key,
        icd_sequence_key=hit_data.icd_sequence_key,
        display_name=display_name,
        area=ImpactAreaSpec(
            shape=hit_data.aoe_shape,
            radius=hit_data.aoe_radius,
            local_offset_xz=hit_data.aoe_offset,
            length=hit_data.aoe_length,
            width=hit_data.aoe_width,
        ),
    )


def compile_normal_attack_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """按资产普攻倍率表编译各命中点的伤害契约（三段为 3A/3B 双命中）。"""

    specs: dict[str, DamageImpactSpec] = {}
    for impact_key, label, component_index, hit_data in ODETTE_NORMAL_ATTACK_DAMAGE_PLANS:
        entry = entries_by_key.get((character_key, "normal_attack", label))
        if entry is None:
            raise ContentUnitValidationError(f"奥黛塔普攻缺少资产倍率条目：{label}")
        specs[impact_key] = _compile_damage_spec(
            impact_key,
            talent_level,
            entry=entry,
            component_index=component_index,
            hit_data=hit_data,
            element_by_amount=False,
            display_name=label,
        )
    return specs


def compile_charged_attack_damage_spec(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> DamageImpactSpec:
    """编译重击伤害契约（衰减序列按 ICD 表修正为「默认」/标签「普通攻击」）。"""

    entry = entries_by_key.get((character_key, "normal_attack", "重击伤害"))
    if entry is None:
        raise ContentUnitValidationError("奥黛塔重击缺少资产倍率条目：重击伤害")
    return _compile_damage_spec(
        ODETTE_CHARGED_ATTACK_IMPACT_KEY,
        talent_level,
        entry=entry,
        component_index=0,
        hit_data=ODETTE_CHARGED_ATTACK_HIT,
        element_by_amount=False,
        display_name="重击伤害",
    )


def compile_elemental_skill_damage_spec(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> DamageImpactSpec:
    """编译元素战技初始段伤害契约（无衰减序列，「元素战技掉球」附加标签）。"""

    entry = entries_by_key.get((character_key, "elemental_skill", "技能伤害"))
    if entry is None:
        raise ContentUnitValidationError("奥黛塔元素战技缺少资产倍率条目：技能伤害")
    return _compile_damage_spec(
        ODETTE_ELEMENTAL_SKILL_IMPACT_KEY,
        talent_level,
        entry=entry,
        component_index=0,
        hit_data=ODETTE_ELEMENTAL_SKILL_HIT,
        display_name="技能伤害",
    )


def compile_elemental_burst_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译元素爆发三段斩击与终结段的伤害契约。"""

    slash_entry = entries_by_key.get((character_key, "elemental_burst", "斩击伤害"))
    if slash_entry is None:
        raise ContentUnitValidationError("奥黛塔元素爆发缺少资产倍率条目：斩击伤害")
    final_entry = entries_by_key.get((character_key, "elemental_burst", "斩击最终段伤害"))
    if final_entry is None:
        raise ContentUnitValidationError("奥黛塔元素爆发缺少资产倍率条目：斩击最终段伤害")
    return {
        ODETTE_ELEMENTAL_BURST_SLASH_1_IMPACT_KEY: _compile_damage_spec(
            ODETTE_ELEMENTAL_BURST_SLASH_1_IMPACT_KEY,
            talent_level,
            entry=slash_entry,
            component_index=0,
            hit_data=ODETTE_BURST_SLASH_1_HIT,
            display_name="斩击伤害",
        ),
        ODETTE_ELEMENTAL_BURST_SLASH_2_IMPACT_KEY: _compile_damage_spec(
            ODETTE_ELEMENTAL_BURST_SLASH_2_IMPACT_KEY,
            talent_level,
            entry=slash_entry,
            component_index=0,
            hit_data=ODETTE_BURST_SLASH_2_HIT,
            display_name="斩击伤害",
        ),
        ODETTE_ELEMENTAL_BURST_SLASH_3_IMPACT_KEY: _compile_damage_spec(
            ODETTE_ELEMENTAL_BURST_SLASH_3_IMPACT_KEY,
            talent_level,
            entry=slash_entry,
            component_index=0,
            hit_data=ODETTE_BURST_SLASH_3_HIT,
            display_name="斩击伤害",
        ),
        ODETTE_ELEMENTAL_BURST_FINAL_IMPACT_KEY: _compile_damage_spec(
            ODETTE_ELEMENTAL_BURST_FINAL_IMPACT_KEY,
            talent_level,
            entry=final_entry,
            component_index=0,
            hit_data=ODETTE_BURST_FINAL_HIT,
            display_name="斩击最终段伤害",
        ),
    }


def compile_plunge_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译下落攻击碰撞与低空/高空落地冲击伤害契约。

    下落攻击走 generic 单手剑通用资料（下坠期间切割、坠地钝击）；落地攻击
    按 ICD 数据为无冷却标签。未获转化时为物理：通用资料的「元素量」仅在
    攻击具元素时生效，规格不携带附着证据。
    """

    collision_entry = entries_by_key.get((character_key, "normal_attack", "下坠期间伤害"))
    if collision_entry is None:
        raise ContentUnitValidationError("奥黛塔下落攻击缺少资产倍率条目：下坠期间伤害")
    landing_entry = entries_by_key.get((character_key, "normal_attack", "低空/高空坠地冲击伤害"))
    if landing_entry is None:
        raise ContentUnitValidationError("奥黛塔下落攻击缺少资产倍率条目：低空/高空坠地冲击伤害")
    landing_compiled = ScalingCompiler.compile_entry(landing_entry, talent_level)
    if len(landing_compiled.components) < 2:
        raise ContentUnitValidationError(
            f"奥黛塔下落攻击落地倍率需要低空/高空两个分量：{len(landing_compiled.components)}"
        )
    collision_data = ODETTE_PLUNGE_ATTACK_DATA.collision
    landing_data = ODETTE_PLUNGE_ATTACK_DATA.landing
    collision_hit = OdetteHitData(
        main_attack_tag=ODETTE_PLUNGE_ATTACK_DATA.main_attack_tag,
        strike_type=collision_data.strike_type,
        range_type=collision_data.range_type,
        aoe_shape=collision_data.aoe_shape,
        aoe_radius=collision_data.aoe_radius,
        aoe_length=0.0,
        aoe_width=0.0,
        aoe_offset=collision_data.aoe_offset,
        icd_tag_key=None,
    )
    landing_hit = OdetteHitData(
        main_attack_tag=ODETTE_PLUNGE_ATTACK_DATA.main_attack_tag,
        strike_type=landing_data.strike_type,
        range_type=landing_data.range_type,
        aoe_shape=landing_data.aoe_shape,
        aoe_radius=landing_data.low_aoe_radius,
        aoe_length=0.0,
        aoe_width=0.0,
        aoe_offset=landing_data.aoe_offset,
        icd_tag_key=None,
    )
    specs = {
        ODETTE_PLUNGE_COLLISION_IMPACT_KEY: _compile_damage_spec(
            ODETTE_PLUNGE_COLLISION_IMPACT_KEY,
            talent_level,
            entry=collision_entry,
            component_index=0,
            hit_data=collision_hit,
            element_by_amount=False,
            display_name="下坠期间伤害",
        ),
        f"{ODETTE_PLUNGE_LANDING_IMPACT_KEY}.low": _compile_damage_spec(
            ODETTE_PLUNGE_LANDING_IMPACT_KEY,
            talent_level,
            entry=landing_entry,
            component_index=0,
            hit_data=replace(landing_hit, aoe_radius=landing_data.low_aoe_radius),
            element_by_amount=False,
            display_name="低空坠地冲击伤害",
        ),
        f"{ODETTE_PLUNGE_LANDING_IMPACT_KEY}.high": _compile_damage_spec(
            ODETTE_PLUNGE_LANDING_IMPACT_KEY,
            talent_level,
            entry=landing_entry,
            component_index=1,
            hit_data=replace(landing_hit, aoe_radius=landing_data.high_aoe_radius),
            element_by_amount=False,
            display_name="高空坠地冲击伤害",
        ),
    }
    return specs


def compile_special_dot_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译破晓终奏持续三段的伤害契约（同一倍率条目、三个影响点）。"""

    entry = entries_by_key.get((character_key, "elemental_skill", "破晓终奏持续伤害"))
    if entry is None:
        raise ContentUnitValidationError("奥黛塔元素战技缺少资产倍率条目：破晓终奏持续伤害")
    specs: dict[str, DamageImpactSpec] = {}
    for impact_key in (
        ODETTE_SPECIAL_DOT_1_IMPACT_KEY,
        ODETTE_SPECIAL_DOT_2_IMPACT_KEY,
        ODETTE_SPECIAL_DOT_3_IMPACT_KEY,
    ):
        specs[impact_key] = _compile_damage_spec(
            impact_key,
            talent_level,
            entry=entry,
            component_index=0,
            hit_data=ODETTE_SPECIAL_DOT_HIT,
            display_name="破晓终奏持续伤害",
        )
    return specs


def compile_dance_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译拂羽/旋翼舞步冰命中伤害契约（按步名键控，供轮换 hook 使用）。

    舞步请求由轮换 hook 在到期帧产出，``impact_ref`` 随请求改写；这里的
    impact_key 只作为契约占位标识。
    """

    plans = (
        (
            ODETTE_DANCE_STEP_PLUME,
            ODETTE_DANCE_PLUME_HIT,
            ODETTE_DANCE_PLUME_IMPACT_KEY,
            "拂羽舞步伤害",
        ),
        (
            ODETTE_DANCE_STEP_WING,
            ODETTE_DANCE_WING_HIT,
            ODETTE_DANCE_WING_IMPACT_KEY,
            "旋翼舞步伤害",
        ),
    )
    specs: dict[str, DamageImpactSpec] = {}
    for step, hit_data, impact_key, label in plans:
        entry = entries_by_key.get((character_key, "elemental_skill", label))
        if entry is None:
            raise ContentUnitValidationError(f"奥黛塔元素战技缺少资产倍率条目：{label}")
        specs[step] = _compile_damage_spec(
            impact_key,
            talent_level,
            entry=entry,
            component_index=0,
            hit_data=hit_data,
            display_name=label,
        )
    return specs


def compile_stellar_channels(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, OdetteStellarChannel]:
    """编译破晓终奏结束段与拂羽/旋翼舞步的星烁通道。

    星超导/星扩散倍率取资产倍率条目「星超导/星扩散伤害」的双分量（分量 0 =
    星超导、分量 1 = 星扩散）；星变体几何/打击/远近按命中数据表星变体行。
    返回键：结束段影响键与舞步步名（plume/wing）。
    """

    end_area = ImpactAreaSpec(
        shape="圆柱",
        radius=4.6,
        local_offset_xz=Vector3(0.0, -1.0, 0.0),
    )
    end_channel = compile_stellar_channel(
        ODETTE_SPECIAL_END_IMPACT_KEY,
        character_key=character_key,
        entries_by_key=entries_by_key,
        talent_key="elemental_skill",
        label="破晓终奏星超导/星扩散伤害",
        talent_level=talent_level,
        conduct_spec=stellar_variant_hit(
            impact_ref=ODETTE_SPECIAL_END_IMPACT_KEY,
            main_attack_tag=STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
            display_name="破晓终奏星超导伤害",
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            area=end_area,
        ),
        swirl_spec=stellar_variant_hit(
            impact_ref=ODETTE_SPECIAL_END_IMPACT_KEY,
            main_attack_tag=STELLAR_SWIRL_ICE_DAMAGE_TAG,
            display_name="破晓终奏星扩散伤害",
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            area=end_area,
        ),
    )
    plume_area = ImpactAreaSpec(
        shape="圆柱",
        radius=4.0,
        local_offset_xz=ODETTE_DANCE_PLUME_HIT.aoe_offset,
    )
    plume_channel = compile_stellar_channel(
        ODETTE_DANCE_PLUME_IMPACT_KEY,
        character_key=character_key,
        entries_by_key=entries_by_key,
        talent_key="elemental_skill",
        label="拂羽舞步星超导/星扩散伤害",
        talent_level=talent_level,
        conduct_spec=stellar_variant_hit(
            impact_ref=ODETTE_DANCE_PLUME_IMPACT_KEY,
            main_attack_tag=STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
            display_name="拂羽舞步星超导伤害",
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            area=plume_area,
        ),
        swirl_spec=stellar_variant_hit(
            impact_ref=ODETTE_DANCE_PLUME_IMPACT_KEY,
            main_attack_tag=STELLAR_SWIRL_ICE_DAMAGE_TAG,
            display_name="拂羽舞步星扩散伤害",
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            area=plume_area,
        ),
    )
    wing_area = ImpactAreaSpec(
        shape="圆柱",
        radius=4.0,
        local_offset_xz=ODETTE_DANCE_WING_HIT.aoe_offset,
    )
    wing_channel = compile_stellar_channel(
        ODETTE_DANCE_WING_IMPACT_KEY,
        character_key=character_key,
        entries_by_key=entries_by_key,
        talent_key="elemental_skill",
        label="旋翼舞步星超导/星扩散伤害",
        talent_level=talent_level,
        conduct_spec=stellar_variant_hit(
            impact_ref=ODETTE_DANCE_WING_IMPACT_KEY,
            main_attack_tag=STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
            display_name="旋翼舞步星超导伤害",
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            area=wing_area,
        ),
        swirl_spec=stellar_variant_hit(
            impact_ref=ODETTE_DANCE_WING_IMPACT_KEY,
            main_attack_tag=STELLAR_SWIRL_ICE_DAMAGE_TAG,
            display_name="旋翼舞步星扩散伤害",
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            area=wing_area,
        ),
    )
    return {
        ODETTE_SPECIAL_END_IMPACT_KEY: end_channel,
        ODETTE_DANCE_STEP_PLUME: plume_channel,
        ODETTE_DANCE_STEP_WING: wing_channel,
    }


class OdetteActionImpactFactory:
    """把奥黛塔动作影响点展开为带伤害契约的 DAMAGE/ENERGY/CREATE 请求。

    ``damage_specs`` 由内容编译期按资产倍率表生成，按 impact_key 索引；
    未登记契约的影响点仍展开为无伤害请求（不结算）。``stellar_channels``
    携带破晓终奏结束段的星烁通道：展开时按辉映证据分派星变体，无辉映证据
    时按星超导变体、星烁基础系数 1 出伤（结束段口径，见 ``stellar.py``）。
    ``c1_channel`` 存在时（C1 已解锁）在同帧追加 C1 追加段；``swan_dream_grant``
    存在时随爆发能量花费展开雪鹄之梦发放。召唤创建影响点展开为 CREATE_ENTITY
    请求。
    """

    def __init__(
        self,
        damage_specs: Mapping[str, DamageImpactSpec],
        *,
        stellar_channels: Mapping[str, OdetteStellarChannel] | None = None,
        splendor_grant: SplendorGrantConfig | None = None,
        swan_dream_grant: SwanDreamGrantConfig | None = None,
        c1_channel: OdetteStellarChannel | None = None,
    ) -> None:
        self._damage_specs = dict(damage_specs)
        self._stellar_channels = dict(stellar_channels or {})
        self._splendor_grant = splendor_grant
        self._swan_dream_grant = swan_dream_grant
        self._c1_channel = c1_channel

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        params: dict[str, object] = {
            "content_handler_key": ODETTE_CHARACTER_HANDLER_KEY,
            "odette": {
                "handler_key": ODETTE_CHARACTER_HANDLER_KEY,
                "source_impact_key": context.impact_key,
            },
        }
        if context.impact_key == ODETTE_SUMMON_CREATE_IMPACT_KEY:
            # 华彩发放随召唤创建同帧展开：先清除全部持有者的旧华彩（重新
            # 召唤语义，对未持层目标是无操作），再创建召唤物、授予新层。
            if self._splendor_grant is None:
                return (self._summon_create_request(context),)
            owner_slot = context.owner.slot
            if owner_slot is None:
                raise OdetteSplendorError("奥黛塔召唤缺少角色归属槽位，无法展开华彩发放")
            reset, grant = summon_grant_requests(
                context,
                self._splendor_grant,
                slot=owner_slot,
            )
            return (reset, self._summon_create_request(context), grant)
        if context.impact_key == ODETTE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY:
            requests = [
                ImpactRequest(
                    frame=context.frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=context.impact_key,
                    owner_slot=context.owner.slot,
                    action_key=context.action_key,
                    source_impact_point_id=context.impact_point_id,
                    target_refs=(f"character:slot_{context.owner.slot}",),
                    params={
                        **params,
                        "energy": {
                            "schema_version": 1,
                            "operation": "spend_burst",
                            "action_instance_id": f"action:{context.source_instance_id}",
                            "tags": (),
                        },
                    },
                )
            ]
            # 雪鹄之梦随爆发施放同帧发放（文本「获得雪鹄之梦」）。
            if self._swan_dream_grant is not None:
                owner_slot = context.owner.slot
                if owner_slot is None:
                    raise OdetteSplendorError("奥黛塔爆发缺少角色归属槽位，无法发放雪鹄之梦")
                requests.append(
                    swan_dream_grant_request(
                        frame=context.frame,
                        slot=owner_slot,
                        definition_key=self._swan_dream_grant.definition_key,
                        duration_frames=self._swan_dream_grant.duration_frames,
                    )
                )
            return tuple(requests)
        if context.impact_key == ODETTE_SPECIAL_RESUME_IMPACT_KEY:
            return (self._special_resume_request(context),)
        damage_spec = self._damage_specs.get(context.impact_key)
        if context.impact_key == ODETTE_SPECIAL_END_IMPACT_KEY:
            return self._special_end_requests(context)
        if damage_spec is None and context.impact_key == ODETTE_PLUNGE_LANDING_IMPACT_KEY:
            variant = context.params.get("plunge_variant")
            if isinstance(variant, str):
                damage_spec = self._damage_specs.get(f"{context.impact_key}.{variant}")
        if damage_spec is not None:
            damage_spec = replace(
                damage_spec,
                impact_ref=f"{context.impact_point_id}:damage",
            )
        return (
            ImpactRequest(
                frame=context.frame,
                kind=ImpactKind.DAMAGE,
                impact_key=context.impact_key,
                owner_slot=context.owner.slot,
                action_key=context.action_key,
                source_impact_point_id=context.impact_point_id,
                target_refs=tuple(target.target_id for target in context.target_refs),
                anchor_entity_id=(
                    ACTIVE_CHARACTER_ENTITY_ID
                    if context.impact_key
                    in {
                        ODETTE_PLUNGE_COLLISION_IMPACT_KEY,
                        ODETTE_PLUNGE_LANDING_IMPACT_KEY,
                    }
                    else None
                ),
                params=params,
                damage_spec=damage_spec,
            ),
        )

    @staticmethod
    def _nearest_target_position(space_runtime: SpaceRuntime, origin: Vector3) -> Vector3:
        """就近敌人位置：与舞步索敌同口径（半径 15、X/Z 就近、并列取实体 id 较小者）。

        没有候选敌人时返回原点，由调用方落在角色位置。
        """

        candidates = space_runtime.entities_in_radius(
            origin,
            ODETTE_DANCE_SEARCH_RADIUS,
            kinds={SpatialEntityKind.TARGET},
        )
        if not candidates:
            return origin
        return min(
            candidates,
            key=lambda entity: (entity.position.distance_xz_to(origin), entity.entity_id),
        ).position

    def _summon_create_request(self, context: ActionImpactContext) -> ImpactRequest:
        """展开独舞倒影创建请求（CREATE_ENTITY）。

        倒影由元素战技向前发射、在命中的敌人处停下；位移过程不实现（规划
        已确认），改为**直接在就近敌人位置生成**——飞行时间不计入时序，因此
        首击锚点（命中帧 +134f）保持不变。元素爆发是「召唤至身边」，仍取
        角色当前位置。附近没有敌人时两种入口都回退到角色位置。

        轮换节奏由创建类型（``dance.py``）接管：请求只携带 type_key 与类型化
        config（施放入口 + Q 是否保留顺序），初始调度在 ``build_state`` 声明，
        E 重召唤重置为拂羽首拍、Q 重召唤已存在时经 ``previous`` 保留拂羽/旋翼
        顺序。索敌以倒影位置为中心，因此停在敌人处等价于「停下后就近攻击」。
        """

        owner_key = f"character:slot_{context.owner.slot}"
        position = Vector3()
        simulation = context.simulation
        if simulation is not None and simulation.space_runtime is not None:
            entity = simulation.space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID)
            origin = entity.position if entity is not None else Vector3()
            position = origin
            if context.action_key == ODETTE_ELEMENTAL_SKILL_ACTION_KEY:
                position = self._nearest_target_position(simulation.space_runtime, origin)
        return ImpactRequest(
            frame=context.frame,
            kind=ImpactKind.CREATE_ENTITY,
            impact_key=context.impact_key,
            owner_slot=context.owner.slot,
            action_key=context.action_key,
            source_impact_point_id=context.impact_point_id,
            target_refs=(),
            params={
                "content_handler_key": ODETTE_CHARACTER_HANDLER_KEY,
                "odette": {
                    "handler_key": ODETTE_CHARACTER_HANDLER_KEY,
                    "source_impact_key": context.impact_key,
                },
                "type_key": ODETTE_DANCE_OBJECT_KEY,
                "duration_frames": ODETTE_DANCE_DURATION_FRAMES,
                "position": {"x": position.x, "y": position.y, "z": position.z},
                "owner_key": owner_key,
                "tags": (ODETTE_DANCE_OBJECT_KEY,),
                "config": {
                    "entry": context.action_key,
                    "preserve_order": context.action_key != ODETTE_ELEMENTAL_SKILL_ACTION_KEY,
                },
            },
        )

    @staticmethod
    def _special_resume_request(context: ActionImpactContext) -> ImpactRequest:
        """展开特殊战技恢复请求（ALIGN_CREATED_ENTITY_TICKS）。

        特殊战技施放 +114f 恢复倒影攻击且不改变舞步顺序：把活动倒影的全部
        tick 调度按同一偏移平移（相位保持），使最早一拍落在施放 +114f。恢复
        影响点在施放次帧展开，目标帧 = 请求帧 + 113。无活动倒影时请求被分发
        器忽略，等价于无需恢复。
        """

        target_frame = (
            context.frame
            + ODETTE_DANCE_RESUME_AFTER_SPECIAL_FRAMES
            - ODETTE_SPECIAL_RESUME_IMPACT_FRAME
        )
        return ImpactRequest(
            frame=context.frame,
            kind=ImpactKind.ALIGN_CREATED_ENTITY_TICKS,
            impact_key=context.impact_key,
            owner_slot=context.owner.slot,
            action_key=context.action_key,
            source_impact_point_id=context.impact_point_id,
            target_refs=(),
            params={
                "content_handler_key": ODETTE_CHARACTER_HANDLER_KEY,
                "odette": {
                    "handler_key": ODETTE_CHARACTER_HANDLER_KEY,
                    "source_impact_key": context.impact_key,
                },
                "type_key": ODETTE_DANCE_OBJECT_KEY,
                "owner_key": f"character:slot_{context.owner.slot}",
                "target_frame": target_frame,
            },
        )

    def _special_end_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        """展开破晓终奏结束段：按辉映证据分派星变体，无证据时按星超导出伤。

        命中数据表该段只有星超导/星扩散两个星变体行（元素量 0）；基础文本
        无条件「视为星超导反应伤害」，辉映只改变变体与基础系数，无辉映证据
        时按星超导变体、星烁基础系数 1 出伤。C1 已解锁时在同帧追加 C1 追加段
        （同口径、倍率取 C1 行、几何取命中表该行、索敌沿用结束段命中集合）。
        星烁输入携带辉映基础系数，P6 基础增伤与雪鹄之梦增伤由伤害修饰
        provider 在结算期产出词条。
        """

        channel = self._stellar_channels.get(ODETTE_SPECIAL_END_IMPACT_KEY)
        if channel is None:
            return ()
        owner_ref = f"character:slot_{context.owner.slot}"
        target_refs = tuple(target.target_id for target in context.target_refs)
        if not target_refs:
            return ()
        stellar_spec = resolve_stellar_variant_spec(
            channel,
            simulation=context.simulation,
            owner_ref=owner_ref,
            frame=context.frame,
            conduct_fallback=True,
        )
        if stellar_spec is None:
            return ()
        requests = [
            self._stellar_request(
                context,
                impact_key=ODETTE_SPECIAL_END_IMPACT_KEY,
                spec=stellar_spec,
                target_refs=target_refs,
            )
        ]
        if self._c1_channel is not None:
            c1_spec = resolve_stellar_variant_spec(
                self._c1_channel,
                simulation=context.simulation,
                owner_ref=owner_ref,
                frame=context.frame,
                conduct_fallback=True,
            )
            if c1_spec is not None:
                requests.append(
                    self._stellar_request(
                        context,
                        impact_key=ODETTE_C1_EXTRA_IMPACT_KEY,
                        spec=c1_spec,
                        target_refs=target_refs,
                    )
                )
        return tuple(requests)

    def _stellar_request(
        self,
        context: ActionImpactContext,
        *,
        impact_key: str,
        spec: DamageImpactSpec,
        target_refs: tuple[str, ...],
    ) -> ImpactRequest:
        """把星变体契约展开为伤害请求（同帧、同命中集合，逐段独立元素量 0）。"""

        request_id = (
            context.impact_point_id
            if impact_key == context.impact_key
            else f"{context.impact_point_id}:c1"
        )
        return ImpactRequest(
            frame=context.frame,
            kind=ImpactKind.DAMAGE,
            impact_key=impact_key,
            owner_slot=context.owner.slot,
            action_key=context.action_key,
            request_id=request_id,
            source_impact_point_id=context.impact_point_id,
            target_refs=target_refs,
            params={
                "content_handler_key": ODETTE_CHARACTER_HANDLER_KEY,
                "odette": {
                    "handler_key": ODETTE_CHARACTER_HANDLER_KEY,
                    "source_impact_key": context.impact_key,
                },
            },
            damage_spec=replace(
                spec,
                impact_ref=f"{request_id}:damage",
            ),
        )
