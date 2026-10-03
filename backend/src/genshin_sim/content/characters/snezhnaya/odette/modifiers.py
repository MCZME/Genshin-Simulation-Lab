"""奥黛塔被动伤害修饰 provider：P5 攻击力曲线与 P6 星烁基础增伤。

包内同构实现：折算方式与槽位消费与桑多涅同名 provider 同构（本切片不跨角色
包 import；第三个星转换角色出现时再评估是否提炼到 ``content/generic/``）。

口径与依据（资产被动文本，规划文档切片 5）：

- **P5 赤忱者的悲歌**「基于奥黛塔攻击力超过1000点的部分，每100点攻击力都将使
  奥黛塔造成的星烁反应伤害额外造成原本1.5%的伤害，至多通过这种方式额外造成
  原本30%的伤害」：文案写「原本」即**整段伤害的乘数**，落在星烁大权区
  （``stellar_authority_multiplier_add``，口径见 D-082 变更记录 2026-10-02 与
  桑多涅 P4 棱晶弹强化/光束加成先例），并按伤害来源自筛为奥黛塔本人（文本限定
  「奥黛塔造成的星烁反应伤害」）。
- **P6 星耀祝礼·银晓之舞**「队伍中的角色触发超导/冰元素扩散反应时，将转为触发
  星超导/星扩散反应，且基于奥黛塔的攻击力，提升队伍中角色造成的上述反应的基础
  伤害：每100点攻击力都将提升0.7%上述反应的基础伤害，至多通过这种方式提升14%
  伤害」：星烁基础增伤槽位（``stellar_base_bonus_add``），**不按来源自筛**
  （文本口径是「队伍中角色造成的」，全队受益），与桑多涅 P6 同款。

两个 provider 都在结算期读 provider owner（奥黛塔）的**实时面板攻击力**，效果行
数值由组装期读入并随 provider 携带（D-082：不得预乘进 ``StellarReactionDamageInput``
基线）。两者都只对星烁完整公式的请求产出词条——专属阶段在别的公式里是越界词条，
provider 自筛 ``formula_key`` 后返回空集合（与超越之匙星烁增伤同款写法）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from genshin_sim.content.characters.snezhnaya.odette.stellar import (
    STELLAR_REACTION_DAMAGE_TAGS,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeSubjectRef,
    ProviderAttributeSubjectScope,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_STELLAR_REACTION,
    DamageAttributeRead,
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope


def _require_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"{label} 必须是数字")
    number = float(value)
    if not math.isfinite(number):
        raise ContentUnitValidationError(f"{label} 必须是有限数字")
    return number


def _require_owner_ref(owner_ref: object, label: str) -> AttributeSubjectRef:
    if not isinstance(owner_ref, str) or not owner_ref.strip():
        raise ContentUnitValidationError(f"{label} owner_ref 必须是非空字符串")
    return AttributeSubjectRef.character(owner_ref)


def _validate_step_and_cap(
    *,
    per_100_atk: float,
    bonus_rate: float,
    cap: float,
    label: str,
) -> None:
    """校验攻击力步长与「每档增伤 / 上限」两分量。

    组件错位（文本内链接编号、持续秒数或邻近分量混入）必须在这里失败，而不是
    静默折算出近零或超大加成：

    - 步长是文本「每 N 点」的 N，是计数（≥ 1）；小于 1 说明取到了比例分量；
    - 增伤比例与上限都是伤害的百分比量，落在 (0, 1] 区间；
    - 「至多通过这种方式提升 X%」是按档数封顶，因此上限必须是每档增伤的**整数倍**
      （比例与上限互换会在此失败）。
    """

    if per_100_atk < 1.0:
        raise ContentUnitValidationError(f"{label} 攻击力步长必须不小于 1（组件错位）")
    if not 0.0 < bonus_rate <= 1.0 or not 0.0 < cap <= 1.0:
        raise ContentUnitValidationError(f"{label} 增伤比例与上限必须在 (0, 1] 区间")
    multiple = cap / bonus_rate
    if not math.isclose(multiple, round(multiple), rel_tol=1e-9, abs_tol=1e-9):
        raise ContentUnitValidationError(f"{label} 上限必须是每档增伤的整数倍（组件错位）")


@dataclass(frozen=True, slots=True)
class OdetteP5AuthorityBonus:
    """P5 星烁大权区加成折算参数。

    ``threshold_atk`` 为起算攻击力（资产行 number_1 = 1000，文本「超过 1000 点
    的部分」），``per_100_atk`` / ``bonus_rate`` / ``cap`` 取自 number_2/3/4。
    """

    threshold_atk: float
    per_100_atk: float
    bonus_rate: float
    cap: float

    def __post_init__(self) -> None:
        label = "P5 星烁大权区加成"
        threshold = _require_number(self.threshold_atk, f"{label} 起算攻击力")
        if threshold < 0.0:
            raise ContentUnitValidationError(f"{label} 起算攻击力不能为负数")
        _validate_step_and_cap(
            per_100_atk=_require_number(self.per_100_atk, f"{label} 攻击力步长"),
            bonus_rate=_require_number(self.bonus_rate, f"{label} 每档增伤比例"),
            cap=_require_number(self.cap, f"{label} 增伤上限"),
            label=label,
        )


@dataclass(frozen=True, slots=True)
class OdetteP6BaseBonus:
    """P6 星烁基础增伤折算参数（步长 / 每档增伤 / 上限）。"""

    per_100_atk: float
    bonus_rate: float
    cap: float

    def __post_init__(self) -> None:
        label = "P6 星烁基础增伤"
        _validate_step_and_cap(
            per_100_atk=_require_number(self.per_100_atk, f"{label} 攻击力步长"),
            bonus_rate=_require_number(self.bonus_rate, f"{label} 每档增伤比例"),
            cap=_require_number(self.cap, f"{label} 增伤上限"),
            label=label,
        )


def authority_bonus_for_atk(atk: float, bonus: OdetteP5AuthorityBonus) -> float:
    """P5 大权区加成：超过起算值的每 ``per_100_atk`` 点攻击力 + ``bonus_rate``，
    至多 ``cap``（线性折算，参数取自资产 P5 效果行）。"""

    excess = atk - bonus.threshold_atk
    if excess <= 0.0:
        return 0.0
    return min(excess / bonus.per_100_atk * bonus.bonus_rate, bonus.cap)


def stellar_base_bonus_for_atk(atk: float, bonus: OdetteP6BaseBonus) -> float:
    """P6 星烁基础增伤：每 ``per_100_atk`` 点攻击力 + ``bonus_rate``，至多
    ``cap``（线性折算，参数取自资产 P6 效果行）。"""

    if atk <= 0.0:
        return 0.0
    return min(atk / bonus.per_100_atk * bonus.bonus_rate, bonus.cap)


class OdetteP5StellarAuthorityProvider:
    """P5：奥黛塔攻击力超过起算值的部分按档提升其星烁反应伤害（大权区乘数）。

    只作用于**奥黛塔本人**造成的星烁反应伤害（含其星变体直伤）；数值与署名经
    ``stellar_authority_multiplier_add`` 词条进入星烁大权区，与冻结基线加算。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        authority_bonus: OdetteP5AuthorityBonus,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(authority_bonus, OdetteP5AuthorityBonus):
            raise ContentUnitValidationError("P5 星烁大权区加成折算参数类型不符")
        self._owner_ref = _require_owner_ref(owner_ref, "P5 星烁大权区加成")
        self._authority_bonus = authority_bonus
        self._provider_key = f"{source_key}.stellar_authority:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            reads=(
                DamageAttributeRead(
                    STAT_ATK_TOTAL,
                    ProviderAttributeSubjectScope.PROVIDER_OWNER,
                ),
            ),
            writes=frozenset({DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD}),
            owner_ref=self._owner_ref,
            display_name=display_name,
        )

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        request = query.request
        if request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        if request.source_ref != self._owner_ref:
            return ()
        if request.main_attack_tag not in STELLAR_REACTION_DAMAGE_TAGS:
            return ()
        atk = float(
            scope.resolve_for_provider(
                STAT_ATK_TOTAL,
                ProviderAttributeSubjectScope.PROVIDER_OWNER,
            ).final_value
        )
        value = authority_bonus_for_atk(atk, self._authority_bonus)
        if value <= 0.0:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD,
                value=value,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )


class OdetteP6StellarBaseBonusProvider:
    """P6：基于奥黛塔攻击力的星烁基础增伤（词条通道，全队受益）。

    增伤按 provider owner（奥黛塔）的实时面板攻击力折算，作用于**全队**造成的
    星烁反应伤害——因此不按伤害来源自筛，只按星烁公式与星烁伤害标签命中。
    折算发生在伤害结算期：数值与署名都通过 ``stellar_base_bonus_add`` 词条进入
    星烁基础增伤槽位，不折叠进 ``StellarReactionDamageInput`` 基线。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        base_bonus: OdetteP6BaseBonus,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(base_bonus, OdetteP6BaseBonus):
            raise ContentUnitValidationError("P6 星烁基础增伤折算参数类型不符")
        self._owner_ref = _require_owner_ref(owner_ref, "P6 星烁基础增伤")
        self._base_bonus = base_bonus
        self._provider_key = f"{source_key}.stellar_base_bonus:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            reads=(
                DamageAttributeRead(
                    STAT_ATK_TOTAL,
                    ProviderAttributeSubjectScope.PROVIDER_OWNER,
                ),
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
        if request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        if request.main_attack_tag not in STELLAR_REACTION_DAMAGE_TAGS:
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
