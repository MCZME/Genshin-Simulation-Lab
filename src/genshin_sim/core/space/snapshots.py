from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.space.entities import SpatialEntity


@dataclass(frozen=True, slots=True)
class SpaceSnapshot:
    """按稳定实体 id 排序的 Space 只读快照。"""

    frame: int
    entity_version: int
    entities: tuple[SpatialEntity, ...]

    def __post_init__(self) -> None:
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("Space snapshot frame 必须是非负整数")
        if (
            isinstance(self.entity_version, bool)
            or not isinstance(self.entity_version, int)
            or self.entity_version < 0
        ):
            raise ValueError("Space snapshot entity_version 必须是非负整数")
        if any(not isinstance(entity, SpatialEntity) for entity in self.entities):
            raise TypeError("Space snapshot entities 必须全部是 SpatialEntity")
        entities = tuple(sorted(self.entities, key=lambda entity: entity.entity_id))
        if len({entity.entity_id for entity in entities}) != len(entities):
            raise ValueError("Space snapshot entities 包含重复 entity_id")
        object.__setattr__(self, "entities", entities)
