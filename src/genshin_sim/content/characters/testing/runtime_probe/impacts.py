from __future__ import annotations

from genshin_sim.content.characters.testing.runtime_probe.constants import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.impacts import (
    ActionImpactContext,
    DamageImpactSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.damage import DamageElement, DamageScalingTerm


class RuntimeProbeImpactFactory:
    """记录 impact 分发已到达 content 的测试工厂。"""

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        params = dict(context.params)
        params["runtime_probe"] = {
            "handler_key": RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
            "source_impact_key": context.impact_key,
        }
        return (
            ImpactRequest(
                frame=context.frame,
                kind=ImpactKind.DAMAGE,
                impact_key=context.impact_key,
                owner_slot=context.owner.slot,
                action_key=context.action_key,
                source_impact_point_id=context.impact_point_id,
                target_refs=tuple(target.target_id for target in context.target_refs),
                params=params,
                damage_spec=DamageImpactSpec(
                    impact_ref=f"{context.impact_point_id}:damage",
                    main_attack_tag="testing.runtime_probe.direct",
                    element=DamageElement.HYDRO,
                    scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
                    can_crit=False,
                    additional_attack_tags=("direct_damage", "testing.runtime_probe"),
                    elemental_strength=AuraStrength.WEAK,
                    elemental_amount=AuraAmount.one(),
                ),
            ),
        )
