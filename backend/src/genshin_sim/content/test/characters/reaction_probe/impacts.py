"""反应探针命中工厂：按键决定的元素直伤 + 弱元素预算。"""

from __future__ import annotations

from genshin_sim.content.test.characters.reaction_probe.constants import (
    REACTION_PROBE_COMPONENT_KEY,
    REACTION_PROBE_MAIN_ATTACK_TAG,
)
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.impacts import (
    ActionImpactContext,
    DamageImpactSpec,
    ImpactKind,
    ImpactRequest,
    StrikeType,
)
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.damage import DamageScalingTerm


class ReactionProbeImpactFactory:
    """按动作参数产出一次探针直伤命中。"""

    def __init__(self, *, handler_key: str) -> None:
        self._handler_key = handler_key

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        params = dict(context.params)
        element = Element(str(params.get("probe_element", Element.HYDRO.value)))
        display_name = params.get("probe_display_name")
        # 物理不携带元素且为钝击；风/岩携带正元素预算但不形成持久 Aura。
        no_aura = element is Element.PHYSICAL
        params["reaction_probe"] = {
            "handler_key": self._handler_key,
            "source_impact_key": context.impact_key,
            "probe_element": element.value,
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
                    main_attack_tag=REACTION_PROBE_MAIN_ATTACK_TAG,
                    element=element,
                    scaling_terms=(
                        DamageScalingTerm(REACTION_PROBE_COMPONENT_KEY, STAT_ATK_TOTAL, 1.0),
                    ),
                    can_crit=True,
                    additional_attack_tags=("direct_damage", "testing.reaction_probe"),
                    strike_type=StrikeType.BLUNT if no_aura else None,
                    elemental_strength=None if no_aura else AuraStrength.WEAK,
                    elemental_amount=AuraAmount.zero() if no_aura else AuraAmount.one(),
                    display_name=display_name if isinstance(display_name, str) else None,
                ),
            ),
        )
