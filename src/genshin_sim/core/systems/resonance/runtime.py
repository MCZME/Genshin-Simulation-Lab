"""元素共鸣运行时：激活集合的只读查询与一次性激活事实发布。"""

from __future__ import annotations

from genshin_sim.core.events import EventEngine, EventType, GameEvent
from genshin_sim.core.events.payloads import ResonanceActivatedPayload
from genshin_sim.core.systems.resonance.snapshots import ResonanceSnapshot
from genshin_sim.core.systems.resonance.store import ResonanceStore


class ResonanceRuntime:
    """元素共鸣领域运行入口。

    激活集合在组装阶段确定；Runtime 只负责只读查询、快照，以及在首次
    帧推进时发布一次 `RESONANCE_ACTIVATED` 事实。
    """

    def __init__(self, store: ResonanceStore, event_engine: EventEngine) -> None:
        self.store = store
        self.event_engine = event_engine
        self._activation_published = False

    @property
    def active_keys(self) -> tuple[str, ...]:
        return self.store.active_keys

    def has(self, key: str) -> bool:
        return key in self.store.active_keys

    def update_frame(self, context, frame: int) -> None:
        del context
        if self._activation_published:
            return
        self._activation_published = True
        composition = self.store.composition
        team_size = 0 if composition is None else composition.team_size
        self.event_engine.publish(
            GameEvent(
                EventType.RESONANCE_ACTIVATED,
                frame,
                ResonanceActivatedPayload(
                    active_keys=self.store.active_keys,
                    team_size=team_size,
                    established_frame=0,
                ),
                self,
            )
        )

    def is_idle(self) -> bool:
        return True

    def snapshot(self, frame: int) -> ResonanceSnapshot:
        composition = self.store.composition
        return ResonanceSnapshot(
            frame=frame,
            active_keys=self.store.active_keys,
            team_size=0 if composition is None else composition.team_size,
            established_frame=0,
            last_electro_particle_frame=self.store.last_electro_particle_frame,
        )

    def try_claim_electro_particle(self, frame: int) -> bool:
        return self.store.try_claim_electro_particle(frame)
