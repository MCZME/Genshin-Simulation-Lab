from __future__ import annotations

from dataclasses import dataclass
from math import hypot


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
            msg = "radius 必须为非负数"
            raise ValueError(msg)

    def contains(self, position: Vector3) -> bool:
        return self.center.distance_xz_to(position) <= self.radius
