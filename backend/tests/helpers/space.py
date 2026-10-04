"""空间领域测试共享的纯构造器与替身。

当前提供创建物运行时测试共用的 ``RecordingCreatedEntityType``：无外部依赖的
测试替身，按调度种子建态并记录每次 ``on_tick`` 调用与其上下文。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.space import (
    CreatedObjectRuntimeState,
    CreatedObjectTickState,
    SpatialEntity,
)


class RecordingCreatedEntityType:
    """测试用创建实体类型：按构造给定的调度种子建态，记录每次 on_tick。

    ``schedule_seeds`` 为 (schedule_key, 首拍偏移, 周期|None) 元组：构建时以
    创建帧换算为绝对 ``next_tick_frame``；on_tick 以原定帧 + 周期自行推进，
    周期为 ``None`` 表示一次性（tick 后停机）。
    """

    def __init__(
        self,
        type_key: str,
        schedule_seeds: Sequence[tuple[str, int, int | None]] = (),
    ) -> None:
        self.type_key = type_key
        self._schedule_seeds = tuple(schedule_seeds)
        self.calls: list[tuple[str, int, str]] = []
        self.contexts: list[SimulationContext] = []

    def build_state(
        self,
        config: Mapping[str, object],
        entity: SpatialEntity,
        frame: int,
        previous: CreatedObjectRuntimeState | None,
    ) -> CreatedObjectRuntimeState:
        del config, previous
        return CreatedObjectRuntimeState(
            entity=entity,
            type_key=self.type_key,
            schedules=tuple(
                CreatedObjectTickState(schedule_key=key, next_tick_frame=frame + offset)
                for key, offset, _interval in self._schedule_seeds
            ),
        )

    def on_tick(
        self,
        state: CreatedObjectRuntimeState,
        schedule: CreatedObjectTickState,
        frame: int,
        context: SimulationContext,
    ) -> tuple[ImpactRequest, ...]:
        self.calls.append((state.entity.entity_id, frame, schedule.schedule_key))
        self.contexts.append(context)
        period = next(p for k, _o, p in self._schedule_seeds if k == schedule.schedule_key)
        schedule.next_tick_frame = None if period is None else frame + period
        return (
            ImpactRequest(
                frame=frame,
                kind=ImpactKind.DAMAGE,
                impact_key=f"{state.type_key}.tick",
                tags=state.entity.tags,
            ),
        )
