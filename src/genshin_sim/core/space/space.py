from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import TYPE_CHECKING

from genshin_sim.core.space.entities import SpatialEntity, SpatialEntityKind
from genshin_sim.core.space.geometry import CircleArea, Vector3

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext

ACTIVE_CHARACTER_ENTITY_ID = "player:active"


class Space:
    """战场空间的最小查询容器。

    当前不模拟移动、碰撞或实体挤压，只提供空间实体登记和 X/Z 平面范围查询。
    """

    def __init__(self, entities: Iterable[SpatialEntity] = ()) -> None:
        self._entities: dict[str, SpatialEntity] = {}
        self._current_frame = 0
        for entity in entities:
            self.add_entity(entity)

    @property
    def entities(self) -> tuple[SpatialEntity, ...]:
        return tuple(self._entities.values())

    def add_entity(self, entity: SpatialEntity) -> SpatialEntity:
        if entity.entity_id in self._entities:
            msg = f"空间实体 id 重复：{entity.entity_id}"
            raise ValueError(msg)
        self._entities[entity.entity_id] = entity
        return entity

    def update_entity(self, entity: SpatialEntity) -> SpatialEntity:
        if entity.entity_id not in self._entities:
            msg = f"未知空间实体 id：{entity.entity_id}"
            raise KeyError(msg)
        self._entities[entity.entity_id] = entity
        return entity

    def get_entity(self, entity_id: str) -> SpatialEntity | None:
        return self._entities.get(entity_id)

    def update_active_character_slot(
        self,
        active_slot: int,
        *,
        entity_id: str = ACTIVE_CHARACTER_ENTITY_ID,
    ) -> SpatialEntity:
        entity = self._entities.get(entity_id)
        if entity is None:
            msg = f"未知空间实体 id：{entity_id}"
            raise KeyError(msg)
        if entity.kind is not SpatialEntityKind.ACTIVE_CHARACTER:
            msg = f"空间实体不是当前场上角色：{entity_id}"
            raise ValueError(msg)
        return self.update_entity(replace(entity, active_slot=active_slot))

    def entities_in_radius(
        self,
        center: Vector3,
        radius: float,
        *,
        kinds: Iterable[SpatialEntityKind] | None = None,
        exclude_entity_ids: Iterable[str] = (),
    ) -> tuple[SpatialEntity, ...]:
        area = CircleArea(center=center, radius=radius)
        return self.entities_in_area(
            area,
            kinds=kinds,
            exclude_entity_ids=exclude_entity_ids,
        )

    def entities_in_area(
        self,
        area: CircleArea,
        *,
        kinds: Iterable[SpatialEntityKind] | None = None,
        exclude_entity_ids: Iterable[str] = (),
    ) -> tuple[SpatialEntity, ...]:
        kind_filter = None if kinds is None else frozenset(kinds)
        excluded = frozenset(exclude_entity_ids)
        return tuple(
            entity
            for entity in self._entities.values()
            if entity.entity_id not in excluded
            and entity.is_active_at(self._current_frame)
            and (kind_filter is None or entity.kind in kind_filter)
            and area.contains(entity.position)
        )

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        del context
        if frame < 0:
            msg = "帧号不能为负数"
            raise ValueError(msg)
        self._current_frame = frame

    def is_idle(self) -> bool:
        return True
