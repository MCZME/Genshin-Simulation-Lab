"""超越之匙被动的伤害修饰：持有「超越」层数时装备者的星超导反应伤害提升。

落点是星烁公式专属阶段 ``stellar_reaction_bonus_add``，按星超导冰/雷两个组分
伤害标签定向（与影中沉凝的幻灭 4 件套同口径：不用 ``reaction_profile_key``
区分——它带方向会漏掉半边；也不用 ``formula_key`` 区分星超导与星扩散）。
加成值按活动层数线性换算：每层一份，层数经装配期注入的
``TargetBuffPresenceReadPort`` 读取，未绑定或无层时不贡献。

复合（星扩散）路径会对每个参与者重新收集修饰，且组分查询的来源主体是该参与者，
因此 ``source_ref`` 自筛保证这份加成只作用于装备者自己的那一份。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.weapons.claymore.a_teaspoon_of_transcendence.data import (
    A_TEASPOON_OF_TRANSCENDENCE_AUDIT_TAG,
)
from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_STELLAR_REACTION
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
    STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG,
)

_STELLAR_SUPERCONDUCT_DAMAGE_TAGS = frozenset(
    {STELLAR_CONDUCT_CRYO_DAMAGE_TAG, STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG}
)


class TranscendenceStellarSuperconductProvider:
    """持有「超越」层数时，装备者造成的星超导反应伤害按层提升。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        bonus_per_layer: float,
        definition_key: str,
        source_key: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("星超导增伤 provider owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("星超导增伤 provider 必须绑定正整数队伍槽位")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._bonus_per_layer = float(bonus_per_layer)
        self._definition_key = definition_key
        self._provider_key = f"{source_key}.stellar_superconduct.slot:{slot}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.STELLAR_REACTION_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name="超越之匙·星超导增伤",
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
        session: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del session
        request = query.request
        if request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        if request.source_ref != self._owner_ref:
            return ()
        if request.main_attack_tag not in _STELLAR_SUPERCONDUCT_DAMAGE_TAGS:
            return ()
        port = self._target_status_port
        if port is None:
            return ()
        stacks = port.active_stack_count(
            target_ref=self._owner_ref,
            definition_key=self._definition_key,
            frame=request.frame,
        )
        if stacks <= 0:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
                value=self._bonus_per_layer * stacks,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(A_TEASPOON_OF_TRANSCENDENCE_AUDIT_TAG,),
            ),
        )
