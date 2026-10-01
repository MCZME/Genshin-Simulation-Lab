"""桑多涅被动与命座的伤害/属性修饰 provider。

- P5 淑女的行事准则：每 100 点攻击力提升 8 点元素精通、至多 160（属性
  provider，攻击力按声明依赖实时读取，攻击力面板变化即时反映到精通）。
- C1 鎏金未凋，夕暮已远：全队星烁反应伤害 +30%（星烁公式专属阶段
  ``stellar_reaction_bonus_add``，全队口径不按来源自筛，覆盖星超导（冰/雷）
  与星扩散（冰/风）全部星烁反应伤害）。
- C2 回望镜中，时岁翩然：重击冷凝射线的星超导冰伤逐射线获得暴伤提升（通用暴伤
  槽位 ``crit_damage_add``；会话序号由法洁欧 hook 以请求附加标签承载，
  provider 只做换算）。

折算口径：P5 按攻击力线性换算后应用上限，不做取整截断。
"""

# 说明：provider 的审计显示名由 C1/C2 效果单元的工厂传入（`f"{效果行名称}·…"`），
# 效果行名称取自资产 `params.name`，本文件不硬编码命座名。

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_RAY_INDEX_FACT_KEY,
    SANDRONE_P4_PRISM_BOOST_FACT_KEY,
    SANDRONE_RAY_STELLAR_ADDITIONAL_TAG,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    ProviderAttributeRead,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.attributes.session import AttributeResolutionSession
from genshin_sim.core.systems.damage import (
    DamageFactValue,
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
    STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
    STELLAR_SWIRL_WIND_DAMAGE_TAG,
)

# C1 星烁反应通用增伤覆盖的星烁伤害标签（星超导与星扩散都可以吃到）：
# 星超导冰/雷、星扩散冰/风，含携带对应标签的星变体直伤与反应本体伤害。
_C1_STELLAR_REACTION_DAMAGE_TAGS = frozenset(
    {
        STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
        STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG,
        STELLAR_SWIRL_ICE_DAMAGE_TAG,
        STELLAR_SWIRL_WIND_DAMAGE_TAG,
    }
)


def _require_positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"{label} 必须是数字")
    number = float(value)
    if number <= 0.0:
        raise ContentUnitValidationError(f"{label} 必须为正数")
    return number


class SandroneAtkToMasteryProvider:
    """P5：装备者面板攻击力按比例转化为元素精通（FLAT_ADD）。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        em_per_100_atk: float,
        em_cap: float,
        source_key: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("P5 攻击转精通 owner_ref 必须是非空字符串")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._em_per_100_atk = _require_positive_number(em_per_100_atk, "P5 每 100 攻击精通")
        self._em_cap = _require_positive_number(em_cap, "P5 精通上限")
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = ModifierProviderSpec(
            provider_key=f"{source_key}.atk_mastery:{owner_ref}",
            reads=(ProviderAttributeRead(STAT_ATK_TOTAL),),
            writes=frozenset({STAT_ELEMENTAL_MASTERY}),
            owner_ref=self._owner_ref,
            display_name="淑女的行事准则·攻击力转精通",
        )

    def contribute(
        self,
        query: AttributeQuery,
        session: object,
    ) -> tuple[ModifierTerm, ...]:
        if query.attribute_key is not STAT_ELEMENTAL_MASTERY:
            return ()
        if query.subject_ref != self._owner_ref:
            return ()
        if not isinstance(session, AttributeResolutionSession):
            raise ContentUnitValidationError("P5 攻击转精通需要属性解析会话")
        atk_resolution = session.resolve_dependency(
            AttributeQuery(
                subject_ref=query.subject_ref,
                attribute_key=STAT_ATK_TOTAL,
                frame=query.frame,
            )
        )
        atk = float(atk_resolution.final_value)
        value = min(atk / 100.0 * self._em_per_100_atk, self._em_cap)
        if value <= 0.0:
            return ()
        return (
            ModifierTerm(
                target_key=STAT_ELEMENTAL_MASTERY,
                stage=ModifierStage.FLAT_ADD,
                value=value,
                provider_key=self.provider_spec.provider_key,
                source_ref=self._source_ref,
            ),
        )


class SandroneC1StellarBonusProvider:
    """C1：全队造成的星烁反应伤害 +30%（星烁公式专属增伤阶段）。

    全队口径：不按来源自筛；覆盖星超导（冰/雷）与星扩散（冰/风）全部
    星烁反应伤害——含携带对应标签的星变体直伤与反应本体伤害（C1 文本
    "星超导反应伤害"按星烁反应通用增伤理解）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        bonus_value: float,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("C1 星烁增伤 owner_ref 必须是非空字符串")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._bonus_value = _require_positive_number(bonus_value, "C1 星烁增伤")
        self._provider_key = f"{source_key}.stellar_bonus:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.STELLAR_REACTION_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name=display_name,
        )

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        request = query.request
        if request.main_attack_tag not in _C1_STELLAR_REACTION_DAMAGE_TAGS:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
                value=self._bonus_value,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )


class SandroneC2RayCritDamageProvider:
    """C2：重击冷凝射线的星超导冰伤按会话序号获得暴伤提升。

    射线会话序号由法洁欧 hook 发射时以请求级事实绑定
    （``sandrone.fageou.ray_index``），provider 声明读取后换算为暴伤加成项
    （+40% 基础 + 20%/射线，至多计入 3 条），非射线或普通射线不命中附加标签。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        crit_damage_base: float,
        crit_damage_per_ray: float,
        max_rays: int,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("C2 射线暴伤 owner_ref 必须是非空字符串")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._crit_damage_base = _require_positive_number(crit_damage_base, "C2 射线暴伤基础值")
        self._crit_damage_per_ray = _require_positive_number(
            crit_damage_per_ray, "C2 逐射线暴伤增量"
        )
        if isinstance(max_rays, bool) or not isinstance(max_rays, int) or max_rays <= 0:
            raise ContentUnitValidationError("C2 暴伤计层上限必须是正整数")
        self._max_rays = max_rays
        self._provider_key = f"{source_key}.ray_crit_damage:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.CRIT_DAMAGE_ADD}),
            owner_ref=self._owner_ref,
            reads_facts=frozenset({FAGEOU_RAY_INDEX_FACT_KEY}),
            display_name=display_name,
        )

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        request = query.request
        if request.source_ref != self._owner_ref:
            return ()
        if request.main_attack_tag != STELLAR_CONDUCT_CRYO_DAMAGE_TAG:
            return ()
        if SANDRONE_RAY_STELLAR_ADDITIONAL_TAG not in request.tags:
            return ()
        ray_index = _ray_index_of(scope.read_fact(FAGEOU_RAY_INDEX_FACT_KEY))
        if ray_index is None:
            return ()
        counted = min(ray_index, self._max_rays)
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.CRIT_DAMAGE_ADD,
                value=self._crit_damage_base + self._crit_damage_per_ray * counted,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )


def _ray_index_of(value: DamageFactValue | None) -> int | None:
    """把事实值收敛为正整数射线序号；非正整数或类型不符时返回 ``None``。"""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


class SandroneP4PrismBoostProvider:
    """P4 悠久的演算机关：第二枚棱晶弹伤害按资产效果行倍率强化。

    施放帧判定（P4 已解锁 ∧ 解算功率 > 阈值 ∧ 施放时持辉映）由 E 动作完成，
    判定结果经影响工厂以请求级事实绑定在第二枚棱晶弹请求上（发射时刻冻结，
    与子弹落点时刻的功率无关）。本 provider 读到该事实后，对请求的每个倍率
    组件产出系数百分比词条：``coefficient × multiplier`` 等价于
    ``percent_add = multiplier - 1``，普通与星烁契约共用同一倍率区阶段
    （D-082），因此一个 provider 同时覆盖两种契约。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        boost_multiplier: float,
        source_key: str,
        display_name: str,
    ) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._boost_multiplier = _require_positive_number(boost_multiplier, "P4 棱晶弹强化倍率")
        self._provider_key = f"{source_key}.prism_boost:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD}),
            owner_ref=self._owner_ref,
            reads_facts=frozenset({SANDRONE_P4_PRISM_BOOST_FACT_KEY}),
            display_name=display_name,
        )

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        request = query.request
        if request.source_ref != self._owner_ref:
            return ()
        if scope.read_fact(SANDRONE_P4_PRISM_BOOST_FACT_KEY) is not True:
            return ()
        return tuple(
            DamageModifierTerm(
                stage=DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD,
                value=self._boost_multiplier - 1.0,
                component_key=term.component_key,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            )
            for term in request.scaling_terms
        )
