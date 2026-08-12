from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from genshin_sim.core.entity_states.lifecycle import EntityLifecycle
from genshin_sim.core.space.geometry import Vector3


@dataclass(frozen=True, slots=True)
class CollisionBox:
    """空间实体碰撞箱。

    当前只支持圆柱：``position.y`` 视为实体基座高度，碰撞箱从基座向上延伸
    ``height``。默认圆柱底半径 ``0.5``、高 ``1.0``。
    """

    shape: str = "圆柱"
    radius: float = 0.5
    height: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.shape, str) or not self.shape.strip():
            raise ValueError("CollisionBox.shape 必须是非空字符串")
        if (
            isinstance(self.radius, bool)
            or not isinstance(self.radius, int | float)
            or self.radius < 0
        ):
            raise ValueError("CollisionBox.radius 必须为非负数")
        if (
            isinstance(self.height, bool)
            or not isinstance(self.height, int | float)
            or self.height < 0
        ):
            raise ValueError("CollisionBox.height 必须为非负数")

    def to_dict(self) -> dict[str, object]:
        return {"shape": self.shape, "radius": self.radius, "height": self.height}


class SpatialEntityKind(StrEnum):
    """空间实体类型。"""

    ACTIVE_CHARACTER = "active_character"
    TARGET = "target"
    CREATED_OBJECT = "created_object"
    REACTION_OBJECT = "reaction_object"


@dataclass(frozen=True, slots=True)
class SpatialEntity:
    """战场空间中的实体。

    这里保存空间身份、生命周期、位置、朝向和基础分类；目标、角色或内容对象的
    复杂战斗状态仍由对应运行态或机制系统保存。
    """

    entity_id: str
    kind: SpatialEntityKind
    position: Vector3
    lifecycle: EntityLifecycle = field(default_factory=EntityLifecycle)
    collision_box: CollisionBox = field(default_factory=CollisionBox)
    facing: Vector3 = Vector3(0.0, 0.0, 1.0)
    active_slot: int | None = None
    owner_key: str | None = None
    source_key: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.entity_id.strip():
            msg = "entity_id 必须是非空字符串"
            raise ValueError(msg)
        if not isinstance(self.kind, SpatialEntityKind):
            msg = "空间实体类型必须是 SpatialEntityKind"
            raise TypeError(msg)
        if not isinstance(self.lifecycle, EntityLifecycle):
            msg = "空间实体生命周期必须是 EntityLifecycle"
            raise TypeError(msg)
        if not isinstance(self.collision_box, CollisionBox):
            msg = "空间实体碰撞箱必须是 CollisionBox"
            raise TypeError(msg)
        if self.active_slot is not None and self.active_slot <= 0:
            msg = "active_slot 必须是正整数"
            raise ValueError(msg)
        if self.owner_key is not None and not self.owner_key.strip():
            msg = "空间实体归属 key 必须是非空字符串"
            raise ValueError(msg)
        if self.source_key is not None and not self.source_key.strip():
            msg = "空间实体来源 key 必须是非空字符串"
            raise ValueError(msg)
        for tag in self.tags:
            if not isinstance(tag, str) or not tag.strip():
                msg = "空间实体标签必须是非空字符串"
                raise ValueError(msg)
        object.__setattr__(self, "tags", tuple(self.tags))

    def is_active_at(self, frame: int) -> bool:
        return self.lifecycle.is_active_at(frame)

    def to_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "kind": self.kind.value,
            "position": self.position.to_dict(),
            "lifecycle": self.lifecycle.to_dict(),
            "collision_box": self.collision_box.to_dict(),
            "facing": self.facing.to_dict(),
            "active_slot": self.active_slot,
            "owner_key": self.owner_key,
            "source_key": self.source_key,
            "tags": list(self.tags),
        }
