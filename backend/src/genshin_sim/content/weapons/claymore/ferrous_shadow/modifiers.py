"""铁影阔剑被动的伤害修饰：生命值低于 70% 期间，重击伤害提升。

落点是通用 ``damage_bonus_add`` 槽位，作用范围由本 provider 自筛主攻击标签
（重击）决定；载体条件（生命低于阈值）经装配期注入的 ``TargetBuffPresenceReadPort``
读取标记 Buff，未绑定或标记不活跃时不贡献。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope


class FerrousShadowChargedBonusProvider:
    """生命值低于阈值期间，装备者的重击伤害提升。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        bonus: float,
        attack_tag: str,
        definition_key: str,
        source_key: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("铁影阔剑 provider owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("铁影阔剑 provider 必须绑定正整数队伍槽位")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._bonus = float(bonus)
        self._attack_tag = attack_tag
        self._definition_key = definition_key
        self._provider_key = f"{source_key}.charged_bonus.slot:{slot}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name="铁影阔剑·不屈",
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
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        request = query.request
        if request.source_ref != self._owner_ref:
            return ()
        if request.main_attack_tag != self._attack_tag:
            return ()
        port = self._target_status_port
        if port is None:
            return ()
        if not port.has_buff(
            target_ref=self._owner_ref,
            definition_key=self._definition_key,
            frame=request.frame,
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=("ferrous_shadow",),
            ),
        )
