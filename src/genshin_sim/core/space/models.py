from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import hypot
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext


@dataclass(frozen=True, slots=True)
class Vector3:
    """三维位置。

    第一版普通范围判定只使用 X/Z 平面，Y 轴保留给下落攻击等高度敏感机制。
    """

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def distance_xz_to(self, other: Vector3) -> float:
        return hypot(self.x - other.x, self.z - other.z)


@dataclass(frozen=True, slots=True)
class CircleArea:
    """X/Z 平面圆形范围。"""

    center: Vector3
    radius: float

    def __post_init__(self) -> None:
        if self.radius < 0:
            msg = "radius must be non-negative"
            raise ValueError(msg)

    def contains(self, position: Vector3) -> bool:
        return self.center.distance_xz_to(position) <= self.radius


@dataclass(frozen=True, slots=True)
class SceneTarget:
    """场景目标的最小运行时表示。"""

    target_id: str
    position: Vector3
    level: int | None = None


class Space:
    """战场空间的最小查询容器。

    当前不模拟移动、碰撞或实体挤压，只提供目标登记和 X/Z 平面范围查询。
    """

    def __init__(self, targets: Iterable[SceneTarget] = ()) -> None:
        self._targets: dict[str, SceneTarget] = {}
        for target in targets:
            self.add_target(target)

    @property
    def targets(self) -> tuple[SceneTarget, ...]:
        return tuple(self._targets.values())

    def add_target(self, target: SceneTarget) -> SceneTarget:
        if target.target_id in self._targets:
            msg = f"duplicate target id: {target.target_id}"
            raise ValueError(msg)
        self._targets[target.target_id] = target
        return target

    def get_target(self, target_id: str) -> SceneTarget | None:
        return self._targets.get(target_id)

    def targets_in_radius(
        self,
        center: Vector3,
        radius: float,
    ) -> tuple[SceneTarget, ...]:
        area = CircleArea(center=center, radius=radius)
        return self.targets_in_area(area)

    def targets_in_area(self, area: CircleArea) -> tuple[SceneTarget, ...]:
        return tuple(target for target in self._targets.values() if area.contains(target.position))

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        del context, frame

    def is_idle(self) -> bool:
        return True
