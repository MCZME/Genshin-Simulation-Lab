from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, hypot


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


@dataclass(frozen=True, slots=True)
class CircleSectorArea:
    """X/Z 平面扇形范围，边界包含在命中范围内。"""

    center: Vector3
    facing: Vector3
    radius: float
    half_angle_degrees: float

    def __post_init__(self) -> None:
        if self.radius < 0:
            raise ValueError("radius 必须为非负数")
        if not 0 <= self.half_angle_degrees <= 180:
            raise ValueError("half_angle_degrees 必须在 0 到 180 之间")
        if self.facing.x == 0 and self.facing.z == 0:
            raise ValueError("扇形 facing 在 X/Z 平面不能为零向量")

    def contains(self, position: Vector3) -> bool:
        distance = self.center.distance_xz_to(position)
        if distance > self.radius:
            return False
        if distance == 0:
            return True
        facing_length = hypot(self.facing.x, self.facing.z)
        dot = self.facing.x * (position.x - self.center.x) + self.facing.z * (
            position.z - self.center.z
        )
        cosine = max(-1.0, min(1.0, dot / (facing_length * distance)))
        return degrees(acos(cosine)) <= self.half_angle_degrees


@dataclass(frozen=True, slots=True)
class OrientedBoxArea:
    """按 facing 旋转的 X/Z 平面矩形，length 是前后完整长度。"""

    center: Vector3
    facing: Vector3
    length: float
    width: float

    def __post_init__(self) -> None:
        if self.length < 0 or self.width < 0:
            raise ValueError("OrientedBox 的 length 和 width 必须为非负数")
        if self.facing.x == 0 and self.facing.z == 0:
            raise ValueError("OrientedBox facing 在 X/Z 平面不能为零向量")

    def contains(self, position: Vector3) -> bool:
        facing_length = hypot(self.facing.x, self.facing.z)
        forward_x = self.facing.x / facing_length
        forward_z = self.facing.z / facing_length
        right_x = -forward_z
        right_z = forward_x
        offset_x = position.x - self.center.x
        offset_z = position.z - self.center.z
        forward = offset_x * forward_x + offset_z * forward_z
        right = offset_x * right_x + offset_z * right_z
        return abs(forward) <= self.length / 2 and abs(right) <= self.width / 2
