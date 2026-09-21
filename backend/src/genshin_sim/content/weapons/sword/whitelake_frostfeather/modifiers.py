"""白湖冬羽被动的伤害修饰：满 3 层时装备者星烁反应伤害的暴击伤害提升。

落点是通用 ``crit_damage_add`` 槽位：星烁伤害的暴击区本来就读取面板暴伤，因此不设
专属阶段，作用范围由本 provider 自筛 ``formula_key`` 决定（与 ``crit_rate_add`` 同模式）。
载体条件（是否满 3 层）经装配期注入的 ``TargetBuffPresenceReadPort`` 读取，未绑定时不贡献。

复合（星扩散）路径会对每个参与者重新收集修饰，且组分查询的来源主体是该参与者，
因此 ``source_ref`` 自筛保证这份加成只作用于装备者自己的那一份。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_STELLAR_REACTION
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession


class WhitelakeFrostfeatherStellarCritDamageProvider:
    """满 3 层时，装备者造成的星烁反应伤害的暴击伤害提升。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        crit_damage: float,
        definition_key: str,
        max_layers: int,
        source_key: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("星烁暴伤 provider owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("星烁暴伤 provider 必须绑定正整数队伍槽位")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._crit_damage = float(crit_damage)
        self._definition_key = definition_key
        self._max_layers = max_layers
        self._provider_key = f"{source_key}.stellar_crit_damage.slot:{slot}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.CRIT_DAMAGE_ADD}),
            owner_ref=self._owner_ref,
            display_name="白湖冬羽·星烁暴伤",
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
        if request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        if request.source_ref != self._owner_ref:
            return ()
        port = self._target_status_port
        if port is None:
            return ()
        if (
            port.active_stack_count(
                target_ref=self._owner_ref,
                definition_key=self._definition_key,
                frame=request.frame,
            )
            < self._max_layers
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.CRIT_DAMAGE_ADD,
                value=self._crit_damage,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=("whitelake_frostfeather",),
            ),
        )
