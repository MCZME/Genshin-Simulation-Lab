from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from genshin_sim.core.actions import CandidateTargetRef
from genshin_sim.core.entity_states import TargetRuntimeCollection
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.simulation.team import TeamRuntimeState
from genshin_sim.core.space.created_objects import CreatedObjectRuntime
from genshin_sim.core.space.entities import SpatialEntity, SpatialEntityKind
from genshin_sim.core.space.geometry import CircleArea, CircleSectorArea, OrientedBoxArea, Vector3
from genshin_sim.core.space.snapshots import SpaceSnapshot
from genshin_sim.core.space.space import Space


class SpaceRuntime(FrameUpdatable):
    """战场空间运行态入口与受控同步接口。"""

    def __init__(
        self,
        *,
        space: Space | None = None,
        team_state: TeamRuntimeState,
        targets: TargetRuntimeCollection | None = None,
        created_object_runtime: CreatedObjectRuntime | None = None,
    ) -> None:
        self.space = space or Space()
        self.team_state = team_state
        self.targets = targets or TargetRuntimeCollection()
        self.created_object_runtime = created_object_runtime or CreatedObjectRuntime()
        self._current_frame = 0

    @property
    def entities(self) -> tuple[SpatialEntity, ...]:
        return self.space.entities

    def add_entity(self, entity: SpatialEntity) -> SpatialEntity:
        return self.space.add_entity(entity)

    def update_entity(self, entity: SpatialEntity) -> SpatialEntity:
        return self.space.update_entity(entity)

    def apply_displacement(
        self,
        entity_id: str,
        position: Vector3,
    ) -> SpatialEntity | None:
        """动作系统独占的位移写入口：更新指定空间实体的位置。

        只有动作产生的位移可以通过本入口写入位置；其他领域来源不得直接修改
        Space 实体位置，需要位移时先形成动作意图。
        """

        if not isinstance(position, Vector3):
            raise TypeError("apply_displacement position 必须是 Vector3")
        entity = self.space.get_entity(entity_id)
        if entity is None:
            return None
        return self.space.update_entity(replace(entity, position=position))

    def get_entity(self, entity_id: str) -> SpatialEntity | None:
        return self.space.get_entity(entity_id)

    def update_active_character_slot(self, active_slot: int) -> SpatialEntity:
        return self.space.update_active_character_slot(active_slot)

    def entities_in_radius(
        self,
        center: Vector3,
        radius: float,
        *,
        kinds: Iterable[SpatialEntityKind] | None = None,
        exclude_entity_ids: Iterable[str] = (),
    ) -> tuple[SpatialEntity, ...]:
        return self.space.entities_in_radius(
            center,
            radius,
            kinds=kinds,
            exclude_entity_ids=exclude_entity_ids,
        )

    def entities_in_area(
        self,
        area: CircleArea | CircleSectorArea | OrientedBoxArea,
        *,
        kinds: Iterable[SpatialEntityKind] | None = None,
        exclude_entity_ids: Iterable[str] = (),
    ) -> tuple[SpatialEntity, ...]:
        return self.space.entities_in_area(
            area,
            kinds=kinds,
            exclude_entity_ids=exclude_entity_ids,
        )

    def resolve_candidate_targets(
        self,
        candidate_entity_ids: tuple[str, ...],
    ) -> tuple[CandidateTargetRef, ...]:
        return tuple(
            CandidateTargetRef(
                spatial_entity_id=entity_id,
                target_id=target.target_id,
            )
            for entity_id in candidate_entity_ids
            if (target := self.targets.get_by_spatial_entity_id(entity_id)) is not None
        )

    def sync_created_objects_to_space(self) -> None:
        for state in self.created_object_runtime.objects:
            self.sync_entity_to_space(state.entity)

    def sync_entity_to_space(self, entity: SpatialEntity) -> None:
        if self.space.get_entity(entity.entity_id) is None:
            self.space.add_entity(entity)
            return
        self.space.update_entity(entity)

    def update_frame(self, context, frame: int) -> None:
        if frame < 0:
            msg = "帧号不能为负数"
            raise ValueError(msg)
        self._current_frame = frame
        self.space.update_frame(context, frame)
        self.sync_created_objects_to_space()

    def snapshot(self, frame: int) -> SpaceSnapshot:
        return self.space.snapshot(frame)

    def is_idle(self) -> bool:
        return self.created_object_runtime.is_idle()
