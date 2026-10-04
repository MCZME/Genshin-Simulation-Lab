"""芭芭拉歌声之环的创建实体类型：双调度（5s 治疗 / 1.5s 接触施湿）。

水环注册为类型化创建实体（``type_key = barbara.ring``）：治疗与施湿各一条
tick 调度，节奏常量见 ``data.py``；调度存储由创建物运行时基座持有，到期
驱动与过期门控亦然。本类型负责解析实例配置（``config.owner_slot``）、声明
初始调度，并在到期帧按调度键推进自身下一拍、产出 HEAL / APPLY_AURA 请求。
环实体跟随当前场上角色（机械字段，由创建请求声明、运行时同步）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_ELEMENTAL_SKILL_RING_HEAL_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_RING_WET_IMPACT_KEY,
    BARBARA_RING_HEAL_FIRST_TICK_OFFSET,
    BARBARA_RING_HEAL_SCHEDULE_KEY,
    BARBARA_RING_HEAL_TICK_INTERVAL,
    BARBARA_RING_OBJECT_KEY,
    BARBARA_RING_WET_FIRST_TICK_OFFSET,
    BARBARA_RING_WET_SCHEDULE_KEY,
    BARBARA_RING_WET_TICK_INTERVAL,
)
from genshin_sim.core.impacts import (
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.space import (
    ACTIVE_CHARACTER_ENTITY_ID,
    CreatedObjectRuntimeState,
    CreatedObjectTickState,
)

if TYPE_CHECKING:
    from genshin_sim.core.simulation.context import SimulationContext
    from genshin_sim.core.space import SpatialEntity


class BarbaraRingRuntimeState(CreatedObjectRuntimeState):
    """歌声之环运行态：在基座上补充实例化配置 owner_slot。"""

    def __init__(
        self,
        *,
        entity: SpatialEntity,
        type_key: str,
        schedules: Sequence[CreatedObjectTickState],
        owner_slot: int,
    ) -> None:
        super().__init__(
            entity=entity,
            type_key=type_key,
            schedules=schedules,
        )
        self.owner_slot = owner_slot


def _owner_slot_from_config(config: Mapping[str, object]) -> int:
    raw = config.get("owner_slot")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        msg = "芭芭拉水环创建配置缺少合法 owner_slot"
        raise ValueError(msg)
    return raw


class BarbaraRingType:
    """歌声之环创建实体类型：配置解析、调度声明与治疗/施湿请求产出。"""

    type_key = BARBARA_RING_OBJECT_KEY

    def __init__(
        self,
        *,
        heal_payload: Mapping[str, object],
        wet_spec: ElementalApplicationSpec,
    ) -> None:
        self._heal_payload = dict(heal_payload)
        self._wet_spec = wet_spec

    def build_state(
        self,
        config: Mapping[str, object],
        entity: SpatialEntity,
        frame: int,
        previous: CreatedObjectRuntimeState | None,
    ) -> CreatedObjectRuntimeState:
        del previous  # 水环节奏固定，刷新即重置调度，无继承语义
        schedules = (
            CreatedObjectTickState(
                schedule_key=BARBARA_RING_HEAL_SCHEDULE_KEY,
                next_tick_frame=frame + BARBARA_RING_HEAL_FIRST_TICK_OFFSET,
            ),
            CreatedObjectTickState(
                schedule_key=BARBARA_RING_WET_SCHEDULE_KEY,
                next_tick_frame=frame + BARBARA_RING_WET_FIRST_TICK_OFFSET,
            ),
        )
        return BarbaraRingRuntimeState(
            entity=entity,
            type_key=self.type_key,
            schedules=schedules,
            owner_slot=_owner_slot_from_config(config),
        )

    def on_tick(
        self,
        state: CreatedObjectRuntimeState,
        schedule: CreatedObjectTickState,
        frame: int,
        context: SimulationContext,
    ) -> Sequence[ImpactRequest]:
        del context
        if not isinstance(state, BarbaraRingRuntimeState):
            msg = "歌声之环 tick 收到非本类型运行态"
            raise ValueError(msg)
        # 推进基于原定 tick 帧（追赶补发按原定节奏落帧）。
        if schedule.schedule_key == BARBARA_RING_HEAL_SCHEDULE_KEY:
            schedule.next_tick_frame = frame + BARBARA_RING_HEAL_TICK_INTERVAL
            return (
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.HEAL,
                    impact_key=BARBARA_ELEMENTAL_SKILL_RING_HEAL_IMPACT_KEY,
                    owner_slot=state.owner_slot,
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
        if schedule.schedule_key == BARBARA_RING_WET_SCHEDULE_KEY:
            schedule.next_tick_frame = frame + BARBARA_RING_WET_TICK_INTERVAL
            return (
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.APPLY_AURA,
                    impact_key=BARBARA_ELEMENTAL_SKILL_RING_WET_IMPACT_KEY,
                    owner_slot=state.owner_slot,
                    request_id=(
                        f"{state.entity.entity_id}:{frame}:"
                        f"{BARBARA_ELEMENTAL_SKILL_RING_WET_IMPACT_KEY}"
                    ),
                    anchor_entity_id=ACTIVE_CHARACTER_ENTITY_ID,
                    elemental_application_spec=self._wet_spec,
                ),
            )
        msg = f"未知的歌声之环调度：{schedule.schedule_key}"
        raise ValueError(msg)
