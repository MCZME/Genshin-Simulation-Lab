"""开发者测试内容共享的伤害修饰 provider 构造器。

伤害修饰索引（``DamageModifierIndex``）对每次结算调用全部注册 provider；
武器、圣遗物等按穿戴者归属的内容单元必须自行过滤 ``source_ref``，
否则会污染其他角色的伤害。测试内容统一通过本模块构造带归属过滤的
静态 provider。
"""

from __future__ import annotations

from collections.abc import Sequence

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.modifiers import StaticDamageModifierProvider
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession


class OwnerScopedStaticDamageModifierProvider(StaticDamageModifierProvider):
    """只对指定归属角色的直伤查询贡献固定修饰项的静态 provider。

    - 按归属过滤：伤害修饰索引对每次结算调用全部 provider，武器/圣遗物
      等按穿戴者归属的内容必须自行过滤 ``source_ref``；
    - 按伤害类型过滤：全部修饰阶段只属于直伤公式，剧变等非直伤查询
      携带任何修饰项都会被公式校验拒绝；
    - 按组件过滤：component 阶段词条只能引用查询实际携带的组件。
    """

    def __init__(
        self,
        provider_spec: DamageModifierProviderSpec,
        terms: Sequence[DamageModifierTerm],
        *,
        owner_ref: AttributeSubjectRef,
    ) -> None:
        super().__init__(provider_spec, terms)
        self._owner_ref = owner_ref

    def contribute(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
    ) -> tuple[DamageModifierTerm, ...]:
        if query.request.source_ref != self._owner_ref:
            return ()
        if query.request.formula_key is not FORMULA_KEY_GENERAL:
            return ()
        components = {term.component_key for term in query.request.scaling_terms}
        return tuple(
            term
            for term in self._terms
            if term.component_key is None or term.component_key in components
        )
