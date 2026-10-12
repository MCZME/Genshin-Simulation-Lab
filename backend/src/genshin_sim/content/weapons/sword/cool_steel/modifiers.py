"""冷刃被动的伤害修饰：对处于水/冰元素影响下的敌人造成的伤害提升。

落点是通用 ``damage_bonus_add`` 槽位。该阶段只属于通用公式，provider 必须按
``formula_key`` 自筛，否则会在反应伤害查询上被
``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败；条件经装配期注入的
``TargetElementAuraReadPort`` 读取，端口未绑定时不贡献。
"""

from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.aura.ports import TargetElementAuraReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope


class CoolSteelAffectedBonusProvider:
    """装备者对处于水元素或冰元素影响下的敌人造成的伤害提升。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        bonus: float,
        elements: Iterable[Element],
        source_key: str,
        audit_tag: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("冷刃 provider owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("冷刃 provider 必须绑定正整数队伍槽位")
        affected_elements = tuple(elements)
        if not affected_elements or any(
            not isinstance(element, Element) for element in affected_elements
        ):
            raise ContentUnitValidationError("冷刃 provider 必须声明受影响元素")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._elements = affected_elements
        self._bonus = float(bonus)
        self._provider_key = f"{source_key}.affected_bonus.slot:{slot}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._audit_tags = (audit_tag,)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name="冷刃·止水融冰",
        )
        self._element_aura_port: TargetElementAuraReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        element_aura_port: TargetElementAuraReadPort,
    ) -> None:
        """装配期注入目标附着只读端口；未绑定时不贡献。"""

        self._element_aura_port = element_aura_port

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        request = query.request
        if request.source_ref != self._owner_ref:
            return ()
        if request.formula_key is not FORMULA_KEY_GENERAL:
            return ()
        if request.target_ref.kind is not AttributeSubjectKind.TARGET:
            return ()
        port = self._element_aura_port
        if port is None:
            return ()
        if not any(
            port.is_affected_by(request.target_ref, element, request.frame)
            for element in self._elements
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=self._audit_tags,
            ),
        )
