from __future__ import annotations

from genshin_sim.content.characters.testing.runtime_probe.constants import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.core.impacts import ActionImpactContext, ImpactKind, ImpactRequest


class RuntimeProbeImpactFactory:
    """记录 impact 分发已到达 content 的测试工厂。"""

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        params = dict(context.params)
        params["runtime_probe"] = {
            "handler_key": RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
            "source_impact_key": context.impact_key,
        }
        params["damage"] = {
            "damage_type": "general",
            "scaling_terms": (
                {
                    "component_key": "atk",
                    "attribute_key": "stat.atk.total",
                    "coefficient": 1.0,
                },
            ),
            "can_crit": False,
            "tags": ("direct_damage", "testing.runtime_probe"),
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
                element="anemo",
                params=params,
            ),
        )
