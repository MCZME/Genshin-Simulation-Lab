from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara.constants import (
    BARBARA_CHARACTER_HANDLER_KEY,
)
from genshin_sim.core.impacts import ActionImpactContext, ImpactKind, ImpactRequest


class BarbaraActionImpactFactory:
    """记录芭芭拉动作影响点已由 content 展开。"""

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        params = dict(context.params)
        params["barbara"] = {
            "handler_key": BARBARA_CHARACTER_HANDLER_KEY,
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
            ),
        )
