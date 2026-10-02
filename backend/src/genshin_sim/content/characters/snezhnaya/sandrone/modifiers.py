"""桑多涅被动与命座的伤害/属性修饰 provider。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_RAY_INDEX_FACT_KEY,
    SANDRONE_P4_PRISM_BOOST_FACT_KEY,
    SANDRONE_P4_TACTICS_STACKS_FACT_KEY,
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
    ProviderAttributeSubjectScope,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.attributes.session import AttributeResolutionSession
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_STELLAR_REACTION,
    DamageAttributeRead,
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

# 星烁反应伤害标签（星超导冰/雷、星扩散冰/风），含携带对应标签的星变体直伤
# 与反应本体伤害。C1「星超导反应伤害」与 P6「上述反应的基础伤害」的覆盖口径
# 均按此集合理解。
_STELLAR_REACTION_DAMAGE_TAGS = frozenset(
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
        if request.main_attack_tag not in _STELLAR_REACTION_DAMAGE_TAGS:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
                value=self._bonus_value,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )


@dataclass(frozen=True, slots=True)
class P6BaseBonus:
    """P6 星烁基础增伤折算参数：每 ``per_100_atk`` 点攻击力 + ``bonus_rate``，
    至多 ``cap``（取自资产 P6 效果行 components，组装期读入、由 provider 携带）。"""

    per_100_atk: float
    bonus_rate: float
    cap: float

    def __post_init__(self) -> None:
        # 比例与上限是伤害的百分比量，落在 (0, 1] 区间；组件错位（文本序号、
        # 持续秒数混入比例位）会在此处失败，而不是静默折算出近零增伤。
        if self.per_100_atk <= 0.0:
            raise ContentUnitValidationError("P6 星烁基础增伤的攻击力步长必须为正数")
        if not 0.0 < self.bonus_rate <= 1.0 or not 0.0 < self.cap <= 1.0:
            raise ContentUnitValidationError("P6 星烁基础增伤比例与上限必须在 (0, 1] 区间")


class SandroneP6StellarBaseBonusProvider:
    """P6 星耀祝礼·唯理为光：基于桑多涅攻击力的星烁基础增伤（词条通道）。

    资产文本「基于桑多涅的攻击力，提升队伍中角色造成的上述反应的基础伤害」：
    增伤按**桑多涅本人**的实时面板攻击力折算（provider owner 作用域读取），
    作用于**全队**造成的星烁反应伤害——因此不按伤害来源自筛，只按星烁伤害
    标签命中（口径与 C1 相同）。折算发生在伤害结算期：数值与署名
    都通过 ``stellar_base_bonus_add`` 词条进入星烁基础增伤槽位，不再于请求
    组装期折叠进 ``StellarReactionDamageInput`` 基线。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        base_bonus: P6BaseBonus,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("P6 星烁基础增伤 owner_ref 必须是非空字符串")
        if not isinstance(base_bonus, P6BaseBonus):
            raise ContentUnitValidationError("P6 星烁基础增伤折算参数类型不符")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._base_bonus = base_bonus
        self._provider_key = f"{source_key}.stellar_base_bonus:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            reads=(
                DamageAttributeRead(STAT_ATK_TOTAL, ProviderAttributeSubjectScope.PROVIDER_OWNER),
            ),
            writes=frozenset({DamageModifierStage.STELLAR_BASE_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name=display_name,
        )

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        request = query.request
        if request.main_attack_tag not in _STELLAR_REACTION_DAMAGE_TAGS:
            return ()
        atk = float(
            scope.resolve_for_provider(
                STAT_ATK_TOTAL,
                ProviderAttributeSubjectScope.PROVIDER_OWNER,
            ).final_value
        )
        value = stellar_base_bonus_for_atk(atk, self._base_bonus)
        if value <= 0.0:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_BASE_BONUS_ADD,
                value=value,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )


def stellar_base_bonus_for_atk(atk: float, base_bonus: P6BaseBonus) -> float:
    """P6 星烁基础增伤：每 ``per_100_atk`` 点攻击力 + ``bonus_rate``，至多
    ``cap``（线性折算，参数取自资产 P6 效果行）。"""

    return min(atk / base_bonus.per_100_atk * base_bonus.bonus_rate, base_bonus.cap)


class SandroneC6StellarAscensionProvider:
    """C6 水仙梦醒，且望晨光：桑多涅造成的星烁反应伤害擢升（词条通道）。

    资产文本「桑多涅造成的所有星烁反应伤害擢升 20%」：按伤害来源自筛为
    桑多涅本人（覆盖其直伤星变体与 C4 协同攻击），经
    ``stellar_ascension_bonus_add`` 词条进入星烁擢升槽位（多个来源加算），
    不再于请求组装期折叠进 ``StellarReactionDamageInput`` 基线。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        ascension_bonus: float,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("C6 星烁擢升 owner_ref 必须是非空字符串")
        if ascension_bonus < 0.0:
            raise ContentUnitValidationError("C6 星烁擢升不能为负数")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._ascension_bonus = ascension_bonus
        self._provider_key = f"{source_key}.stellar_ascension:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD}),
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
        if request.source_ref != self._owner_ref:
            return ()
        if request.main_attack_tag not in _STELLAR_REACTION_DAMAGE_TAGS:
            return ()
        if self._ascension_bonus <= 0.0:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD,
                value=self._ascension_bonus,
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
    与子弹落点时刻的功率无关）。

    provider 按 ``formula_key`` 自筛：判定条件要求施放时持辉映，强化因此只应
    发生在切到星变体的第二枚棱晶弹上。但判定帧在施放帧、变体分派在展开帧，两者
    相隔数十帧，辉映可能在中间到期——此时请求走通用公式，而通用公式白名单不含
    大权区阶段，不筛选会被阶段校验当成 provider 违规抛错。
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
            writes=frozenset({DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD}),
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
        if request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        if scope.read_fact(SANDRONE_P4_PRISM_BOOST_FACT_KEY) is not True:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD,
                value=self._boost_multiplier - 1.0,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )


class SandroneP4BeamBonusProvider:
    """P4 悠久的演算机关：辉映下施放爆发后，聚能光束伤害按消费层数放大。

    官方文本「光束造成原本 100% + 清除层数 × 10% 的伤害」= 原本伤害 ×
    (100% + 层数 × 10%)，即一个**乘数**：落在星烁公式的**大权区乘数**
    （``stellar_authority_multiplier``）上，从冻结基线 1.0 加算
    ``每层倍率 × 层数``。资产行的 100% 基座就是该冻结基线本身、不构成贡献，
    内容侧不提取该分量（资产行保留原文数值以追溯官方文本）。

    判定输入是 Q 施放帧消费改进战术得到的**层数**（请求级事实，由影响工厂在
    展开聚能光束星变体请求时绑定）；事实只在真正切到星变体时存在，因此本
    provider 无需自行判定辉映状态。层数换算与署名发生在伤害侧（D-082）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        bonus_per_stack: float,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("P4 光束加成 owner_ref 必须是非空字符串")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._bonus_per_stack = _require_positive_number(bonus_per_stack, "P4 光束每层加成")
        self._provider_key = f"{source_key}.beam_bonus:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD}),
            owner_ref=self._owner_ref,
            reads_facts=frozenset({SANDRONE_P4_TACTICS_STACKS_FACT_KEY}),
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
        stacks = _tactics_stacks_of(scope.read_fact(SANDRONE_P4_TACTICS_STACKS_FACT_KEY))
        if stacks is None:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD,
                value=self._bonus_per_stack * stacks,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )


def _tactics_stacks_of(value: DamageFactValue | None) -> int | None:
    """把事实值收敛为正整数消费层数；非正整数或类型不符时返回 ``None``。"""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value
