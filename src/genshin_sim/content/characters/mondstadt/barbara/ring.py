"""芭芭拉歌声之环的创建物 tick 行为。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_ELEMENTAL_SKILL_RING_HEAL_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_RING_WET_IMPACT_KEY,
)
from genshin_sim.core.impacts import (
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.space import (
    ACTIVE_CHARACTER_ENTITY_ID,
    CreatedObjectRuntimeState,
)


def _owner_slot(state: CreatedObjectRuntimeState) -> int:
    raw = state.params.get("owner_slot")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        msg = "芭芭拉水环创建物缺少合法 owner_slot"
        raise ValueError(msg)
    return raw


class BarbaraRingHealBehavior:
    """每 5s 为当前场上角色产出一次 HEAL 请求。"""

    def __init__(self, heal_payload: Mapping[str, object]) -> None:
        self._heal_payload = dict(heal_payload)

    def create_tick_requests(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
    ) -> Sequence[ImpactRequest]:
        return (
            ImpactRequest(
                frame=frame,
                kind=ImpactKind.HEAL,
                impact_key=BARBARA_ELEMENTAL_SKILL_RING_HEAL_IMPACT_KEY,
                owner_slot=_owner_slot(state),
                request_id=(
                    f"{state.entity.entity_id}:{frame}:"
                    f"{BARBARA_ELEMENTAL_SKILL_RING_HEAL_IMPACT_KEY}"
                ),
                anchor_entity_id=ACTIVE_CHARACTER_ENTITY_ID,
                params={
                    "heal": dict(self._heal_payload),
                },
            ),
        )


class BarbaraRingWetBehavior:
    """每 1.5s 以当前角色为锚点对范围内角色与敌人施加潮湿。"""

    def __init__(self, wet_spec: ElementalApplicationSpec) -> None:
        self._wet_spec = wet_spec

    def create_tick_requests(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
    ) -> Sequence[ImpactRequest]:
        return (
            ImpactRequest(
                frame=frame,
                kind=ImpactKind.APPLY_AURA,
                impact_key=BARBARA_ELEMENTAL_SKILL_RING_WET_IMPACT_KEY,
                owner_slot=_owner_slot(state),
                request_id=(
                    f"{state.entity.entity_id}:{frame}:"
                    f"{BARBARA_ELEMENTAL_SKILL_RING_WET_IMPACT_KEY}"
                ),
                anchor_entity_id=ACTIVE_CHARACTER_ENTITY_ID,
                elemental_application_spec=self._wet_spec,
            ),
        )
