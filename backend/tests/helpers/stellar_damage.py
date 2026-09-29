"""星烁伤害测试共享的合成构造器与修饰 provider 替身。

只实现接线所需的最小行为，不携带真实资产数值（见测试规范 §3.2）。两个星烁关注点
（共享暴伤槽位进入暴击区、复合伤害的逐参与者修饰收集）共用本模块，避免脚手架复制。
"""

from __future__ import annotations

from typing import Any, cast

from genshin_sim.core.attributes import (
    RESISTANCE_ELECTRO,
    STAT_ELEMENTAL_MASTERY,
    AttributeQueryContext,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_STELLAR_REACTION,
    DamageModifierStage,
    DamageQuery,
    DamageRequest,
    StellarReactionDamageInput,
)
from genshin_sim.core.systems.damage.models import DamageModifierTerm
from genshin_sim.core.systems.damage.modifiers import DamageModifierProviderSpec
from genshin_sim.core.systems.damage.stellar import StellarReactionParticipantInput

SOURCE = AttributeSubjectRef.character("character:slot_1")
OTHER = AttributeSubjectRef.character("character:slot_2")
TARGET = AttributeSubjectRef.target("target:star")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar")

CRIT_DAMAGE_STAGE = DamageModifierStage.CRIT_DAMAGE_ADD
STELLAR_BONUS_STAGE = DamageModifierStage.STELLAR_REACTION_BONUS_ADD
STELLAR_AUTHORITY_STAGE = DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD


def make_attribute_resolver() -> AttributeResolver:
    """两个角色各 200 精通、目标 0 电抗的最小属性环境。"""

    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            tuple(
                (
                    subject,
                    BaseAttributeContribution(
                        STAT_ELEMENTAL_MASTERY,
                        200.0,
                        SOURCE_CONTEXT,
                    ),
                )
                for subject in (SOURCE, OTHER)
            )
            + (
                (
                    TARGET,
                    BaseAttributeContribution(RESISTANCE_ELECTRO, 0.0, SOURCE_CONTEXT),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def make_query(stellar_reaction: StellarReactionDamageInput) -> DamageQuery:
    """以 ``SOURCE`` 为最外层来源的星烁伤害查询。"""

    request = DamageRequest(
        request_id="request:stellar",
        frame=0,
        formula_key=FORMULA_KEY_STELLAR_REACTION,
        main_attack_tag="星超导雷",
        impact_key="impact:stellar",
        source_ref=SOURCE,
        target_ref=TARGET,
        source_level=90,
        target_level=90,
        element=Element.ELECTRO,
        source_context=SOURCE_CONTEXT,
        stellar_reaction=stellar_reaction,
    )
    tags = request.tags
    return DamageQuery(
        request=request,
        source_attribute_context=AttributeQueryContext(tags=tags, target_ref=TARGET),
        target_attribute_context=AttributeQueryContext(
            tags=tags, source_ref=SOURCE_CONTEXT, target_ref=SOURCE
        ),
    )


def make_character_direct_input() -> StellarReactionDamageInput:
    return StellarReactionDamageInput(
        mode="character_direct",
        scaling_value=100.0,
        stellar_base_multiplier=1.0,
    )


def make_composite_input() -> StellarReactionDamageInput:
    """两名等值参与者（``SOURCE``、``OTHER``）的复合星烁伤害。"""

    return StellarReactionDamageInput(
        mode="reaction_composite",
        scaling_value=0.0,
        stellar_base_multiplier=1.0,
        participants=(
            StellarReactionParticipantInput(
                participant_ref=SOURCE,
                source_level=90,
                reaction_base_value=100.0,
            ),
            StellarReactionParticipantInput(
                participant_ref=OTHER,
                source_level=90,
                reaction_base_value=100.0,
            ),
        ),
    )


class OwnerScopedProvider:
    """按伤害来源自筛的 provider：只对自己作为来源的那份伤害贡献词条。

    同时自筛公式键，用来锁住「组分查询继承整次请求的公式键」这一行为：
    若组分查询退回 ``general``，本替身会在组分收集里静默返回空。
    """

    def __init__(
        self,
        owner_ref: AttributeSubjectRef,
        stage: DamageModifierStage,
        value: float,
    ) -> None:
        self._owner_ref = owner_ref
        self._stage = stage
        self._value = value
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=f"test.{stage.value}.{owner_ref.entity_id}",
            writes=frozenset({stage}),
            owner_ref=owner_ref,
        )

    def contribute(self, query: DamageQuery, session: Any) -> tuple[DamageModifierTerm, ...]:
        del session
        if query.request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        if query.request.source_ref != self._owner_ref:
            return ()
        return (
            DamageModifierTerm(
                stage=self._stage,
                value=self._value,
                provider_key=self.provider_spec.provider_key,
                source_ref=SOURCE_CONTEXT,
            ),
        )


class TeamWideProvider:
    """队伍级 provider：不按来源自筛、只自筛公式键，对每个组分各贡献一次。

    对应「炉火融炼之心 4 件套」的真实模式：加成对全队星烁伤害生效，
    因此同样依赖组分查询继承公式键。
    """

    def __init__(self, stage: DamageModifierStage, value: float) -> None:
        self._stage = stage
        self._value = value
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=f"test.team.{stage.value}",
            writes=frozenset({stage}),
        )

    def contribute(self, query: DamageQuery, session: Any) -> tuple[DamageModifierTerm, ...]:
        del session
        if query.request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        return (
            DamageModifierTerm(
                stage=self._stage,
                value=self._value,
                provider_key=self.provider_spec.provider_key,
                source_ref=SOURCE_CONTEXT,
            ),
        )


def components_of(result: Any) -> tuple[Any, ...]:
    """取出伤害结果的复合组分审计。"""

    stellar = result.stellar_reaction_resolution
    assert stellar is not None
    return tuple(cast(Any, stellar).components)
