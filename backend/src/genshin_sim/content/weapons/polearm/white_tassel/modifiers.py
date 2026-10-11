"""白缨枪被动的伤害修饰：普通攻击造成的伤害提升。

落点是通用 ``damage_bonus_add`` 槽位，作用范围由本 provider 自筛主攻击标签
（普通攻击）决定；来源自筛保证只作用于装备者自己的伤害结算。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope


class WhiteTasselAttackBonusProvider:
    """装备者的普通攻击造成的伤害提升。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        bonus: float,
        attack_tag: str,
        source_key: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("白缨枪 provider owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("白缨枪 provider 必须绑定正整数队伍槽位")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._bonus = float(bonus)
        self._attack_tag = attack_tag
        self._provider_key = f"{source_key}.attack_bonus.slot:{slot}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name="白缨枪·锐利",
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
        if request.main_attack_tag != self._attack_tag:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=("white_tassel",),
            ),
        )
