"""影中沉凝的幻灭圣遗物套装实现。

资产数据来源：Project Amber / Yatta 当前默认数据（``artifact_set:15046``）。

效果与落点：

- 2 件套：攻击力提高 18% -> ``stat.atk.total`` 的 ``percent_add``，
  静态绑定穿戴者。
- 4 件套 C1：超导反应造成的伤害提升 80% -> 剧变公式专属阶段
  ``transformative_reaction_bonus_add``。
- 4 件套 C2：星超导反应造成的伤害提升 40% -> 星烁公式专属阶段
  ``stellar_reaction_bonus_add``。
- 4 件套 C3：装备者攻击受到超导或星超导反应影响的敌人时，本次攻击暴击率
  提高 16% -> 通用阶段 ``crit_rate_add``。

行为约定：

- 4 件套三段都是「瞬时作用于一次伤害」，一律用伤害系统的修饰项实现，
  **不落 Buff**：``crit_rate_add`` 的契约语义就是「只参与本次伤害的暴击率
  调整」，写进面板或做成有生命周期的 Buff 都会把作用域放大到多次伤害。
- 三个伤害 provider 都按 ``source_ref`` 过滤穿戴者，不同穿戴者互不污染。
- C1 / C2 用 ``main_attack_tag`` 区分反应类型，**不用** ``reaction_profile_key``
  （后者带方向，会漏掉半边），也不依赖 ``formula_key`` 区分星超导与星扩散
  （星烁复合模式的组分查询走通用公式）。
- C3 的目标状态经装配期注入的 ``TargetBuffPresenceReadPort`` 读取；未绑定时
  返回空，因此装配完成前不会生效。
- 每个 provider 都自筛公式：越界阶段会被 ``_validate_formula_stages`` 硬拒绝
  并让整次结算失败，而不是静默跳过。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
)
from genshin_sim.core.coordination.elemental_reaction.status import (
    SUPERCONDUCT_BUFF_DEFINITION_KEY,
)
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import (
    FORMULA_KEY_GENERAL,
    FORMULA_KEY_STELLAR_REACTION,
    FORMULA_KEY_TRANSFORMATIVE_REACTION,
)
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
    STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.superconduct.mechanic import (
    SUPERCONDUCT_DAMAGE_TAG,
)

DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY = "artifact.disenchantment_in_deep_shadow"
DISENCHANTMENT_IN_DEEP_SHADOW_CONTENT_VERSION = "dev-disenchantment-in-deep-shadow"

DISENCHANTMENT_IN_DEEP_SHADOW_2P_AUDIT_TAG = "disenchantment_in_deep_shadow_2p"
DISENCHANTMENT_IN_DEEP_SHADOW_4P_AUDIT_TAG = "disenchantment_in_deep_shadow_4p"


def create_disenchantment_in_deep_shadow_content_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """把影中沉凝的幻灭套装效果 payload 编译为 ContentUnit（按件数分支）。"""

    if request.artifact_kind != "artifact_set_bonus":
        raise ContentUnitValidationError(
            f"{DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY} 只绑定套装效果，不绑定套装行"
        )
    if request.piece_count == 2:
        return _create_two_piece_unit(request)
    if request.piece_count == 4:
        return _create_four_piece_unit(request)
    raise ContentUnitValidationError(
        f"{DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY} 不支持 {request.piece_count} 件套"
    )


def _owner_ref(slot: int) -> str:
    return f"character:slot_{slot}"


def _source_ref(scope: str, slot: int) -> RuntimeSourceRef:
    return RuntimeSourceRef(
        RuntimeSourceKind.CONTENT,
        f"{DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY}:{scope}:slot:{slot}",
    )


def _create_two_piece_unit(request: ArtifactContentUnitRequest) -> ContentUnit:
    (atk_percent,) = _parse_component_values(
        request.params,
        count=1,
        purpose="2 件套攻击力加成",
    )
    subject_ref = AttributeSubjectRef.character(_owner_ref(request.slot))
    provider_key = f"{DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY}.2p.atk_percent.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({STAT_ATK_TOTAL}),
            owner_ref=subject_ref,
            display_name="影中沉凝的幻灭 2件套",
        ),
        (
            ModifierTerm(
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                value=atk_percent,
                provider_key=provider_key,
                source_ref=_source_ref("2p", request.slot),
                audit_tags=(DISENCHANTMENT_IN_DEEP_SHADOW_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY,
        version=DISENCHANTMENT_IN_DEEP_SHADOW_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "disenchantment_in_deep_shadow_2p"},
    )


def _create_four_piece_unit(request: ArtifactContentUnitRequest) -> ContentUnit:
    superconduct_bonus, stellar_conduct_bonus, crit_rate = _parse_component_values(
        request.params,
        count=3,
        purpose="4 件套超导增伤/星超导增伤/条件暴击率",
    )
    owner_ref = _owner_ref(request.slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY,
        version=DISENCHANTMENT_IN_DEEP_SHADOW_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=(
            DisenchantmentInDeepShadowReactionBonusProvider(
                owner_ref=owner_ref,
                slot=request.slot,
                scope="superconduct",
                stage=DamageModifierStage.TRANSFORMATIVE_REACTION_BONUS_ADD,
                formula_key=FORMULA_KEY_TRANSFORMATIVE_REACTION,
                main_attack_tags=frozenset({SUPERCONDUCT_DAMAGE_TAG}),
                bonus=superconduct_bonus,
                display_name="影中沉凝的幻灭 4件套·超导增伤",
            ),
            DisenchantmentInDeepShadowReactionBonusProvider(
                owner_ref=owner_ref,
                slot=request.slot,
                scope="stellar_conduct",
                stage=DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
                formula_key=FORMULA_KEY_STELLAR_REACTION,
                main_attack_tags=frozenset(
                    {STELLAR_CONDUCT_CRYO_DAMAGE_TAG, STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG}
                ),
                bonus=stellar_conduct_bonus,
                display_name="影中沉凝的幻灭 4件套·星超导增伤",
            ),
            DisenchantmentInDeepShadowCritRateProvider(
                owner_ref=owner_ref,
                slot=request.slot,
                crit_rate=crit_rate,
            ),
        ),
        metadata={"piece_count": 4, "purpose": "disenchantment_in_deep_shadow_4p"},
    )


class DisenchantmentInDeepShadowReactionBonusProvider:
    """4 件套 C1 / C2：装备者造成的指定反应伤害提升。

    只对「装备者本人作为来源」且 ``main_attack_tag`` 命中指定反应标签集合的
    查询贡献对应公式的专属阶段，因此天然区分超导与星超导、也不会误命中星扩散。
    星超导直伤按伤害元素拆冰/雷两个标签，故用集合承接。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        scope: str,
        stage: DamageModifierStage,
        formula_key: str,
        main_attack_tags: frozenset[str],
        bonus: float,
        display_name: str,
    ) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._stage = stage
        self._formula_key = formula_key
        self._main_attack_tags = frozenset(main_attack_tags)
        self._bonus = bonus
        self._provider_key = f"{DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY}.4p.{scope}.slot:{slot}"
        self._source_ref = _source_ref(f"4p:{scope}", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({stage}),
            owner_ref=self._owner_ref,
            display_name=display_name,
        )

    def contribute(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
    ) -> tuple[DamageModifierTerm, ...]:
        del session
        request = query.request
        if request.source_ref != self._owner_ref:
            return ()
        if request.formula_key != self._formula_key:
            return ()
        if request.main_attack_tag not in self._main_attack_tags:
            return ()
        return (
            DamageModifierTerm(
                stage=self._stage,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(DISENCHANTMENT_IN_DEEP_SHADOW_4P_AUDIT_TAG,),
            ),
        )


class DisenchantmentInDeepShadowCritRateProvider:
    """4 件套 C3：攻击受到超导或星超导反应影响的敌人时，本次攻击暴击率提高。

    ``crit_rate_add`` 只属于通用公式；必须自筛公式，否则会在反应伤害查询上
    被 ``_validate_formula_stages`` 硬拒绝并让整次结算失败。

    条件判定只查一个 Buff 定义：普通超导与星超导极星辉域施加的是同一个
    ``buff.reaction.superconduct.physical_resistance_reduction``，因此两种来源
    都满足文案的「超导**或**星超导」，无需区分来源。
    """

    def __init__(self, *, owner_ref: str, slot: int, crit_rate: float) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._crit_rate = crit_rate
        self._provider_key = f"{DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY}.4p.crit_rate.slot:{slot}"
        self._source_ref = _source_ref("4p:crit_rate", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.CRIT_RATE_ADD}),
            owner_ref=self._owner_ref,
            display_name="影中沉凝的幻灭 4件套·条件暴击率",
        )
        self._target_status_port: TargetBuffPresenceReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        target_status_port: TargetBuffPresenceReadPort,
    ) -> None:
        """装配期注入目标状态只读端口；未绑定时不贡献。"""

        self._target_status_port = target_status_port

    def contribute(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
    ) -> tuple[DamageModifierTerm, ...]:
        del session
        request = query.request
        if request.source_ref != self._owner_ref:
            return ()
        if request.formula_key is not FORMULA_KEY_GENERAL:
            return ()
        if request.target_ref.kind is not AttributeSubjectKind.TARGET:
            return ()
        port = self._target_status_port
        if port is None:
            return ()
        if not port.has_buff(
            target_ref=request.target_ref,
            definition_key=SUPERCONDUCT_BUFF_DEFINITION_KEY,
            frame=request.frame,
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.CRIT_RATE_ADD,
                value=self._crit_rate,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(DISENCHANTMENT_IN_DEEP_SHADOW_4P_AUDIT_TAG,),
            ),
        )


def _parse_component_values(
    params: Mapping[str, object],
    *,
    count: int,
    purpose: str,
) -> tuple[float, ...]:
    """从套装效果 params 读取数值列表（与正式内容 components 约定一致）。"""

    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes))
        or len(components) < count
    ):
        raise ContentUnitValidationError(f"{purpose} 缺少 components 参数")
    values: list[float] = []
    for index in range(count):
        component = components[index]
        if not isinstance(component, Mapping):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 必须是对象")
        raw_values = component.get("values")
        if (
            not isinstance(raw_values, Sequence)
            or isinstance(raw_values, (str, bytes))
            or not raw_values
        ):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 缺少 values")
        value = raw_values[0]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须是数字")
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须为正数")
        values.append(number)
    return tuple(values)
