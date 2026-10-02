from __future__ import annotations

from dataclasses import dataclass, field
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

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}


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

    @classmethod
    def along_ray(
        cls,
        origin: Vector3,
        direction: Vector3,
        *,
        length: float,
        width: float,
    ) -> OrientedBoxArea:
        """构造从 ``origin`` 沿 ``direction`` 延伸的长条矩形（等宽穿透条）。

        盒体覆盖 ``forward ∈ [0, length]``（``forward`` 为沿射线的投影距离），
        盒心因此落在 ``origin + direction × length / 2``；``direction`` 只取
        X/Z 分量并归一化，零向量报错。横向判据是恒定的 ``width / 2`` 半宽，
        与按各实体自身碰撞半径判定的 ``Space.ray_hits`` 是两种不同语义。
        """

        forward_x, forward_z = _attack_frame(direction)
        half = length / 2
        return cls(
            center=Vector3(
                x=origin.x + forward_x * half,
                y=origin.y,
                z=origin.z + forward_z * half,
            ),
            facing=Vector3(x=forward_x, y=0.0, z=forward_z),
            length=length,
            width=width,
        )

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


@dataclass(frozen=True, slots=True)
class RayQuery:
    """X/Z 平面射线查询规格。

    ``direction`` 在构造期按 X/Z 归一化（Y 分量忽略），零向量报错；
    ``max_distance`` 为 ``None`` 表示不设射程上限，否则命中要求
    ``0 < forward <= max_distance``。射线与实体的横向判定不在本规格中
    表达：查询侧按各实体自身的碰撞半径绕线判定。
    """

    origin: Vector3
    direction: Vector3
    max_distance: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.origin, Vector3):
            raise ValueError("RayQuery.origin 必须是 Vector3")
        if not isinstance(self.direction, Vector3):
            raise ValueError("RayQuery.direction 必须是 Vector3")
        length = hypot(self.direction.x, self.direction.z)
        if length == 0.0:
            raise ValueError("RayQuery.direction 在 X/Z 平面不能为零向量")
        object.__setattr__(
            self,
            "direction",
            Vector3(
                x=self.direction.x / length,
                y=0.0,
                z=self.direction.z / length,
            ),
        )
        if self.max_distance is None:
            return
        if (
            isinstance(self.max_distance, bool)
            or not isinstance(self.max_distance, int | float)
            or self.max_distance < 0
        ):
            raise ValueError("RayQuery.max_distance 必须为 None 或非负数")


@dataclass(frozen=True, slots=True)
class ImpactAreaSpec:
    """未锚定的伤害 AOE 规格。

    ``shape`` 保留资料原始形状文本（如“球”“圆柱”“攻击盒”），运行时按当前
    X/Z 模型投影：球与圆柱都投影为同半径 Circle（高度忽略）；攻击盒投影为
    随攻击方向旋转的 OrientedBox，``length`` 是前后完整边长、``width`` 是左右
    完整边长，资料第三分量（高度）不参与查询。``local_offset_xz`` 是相对锚点
    的本地偏移，投影时随攻击方向旋转到世界系，Y 轴分量保留但不参与查询。
    """

    shape: str
    radius: float
    local_offset_xz: Vector3 = field(default_factory=Vector3)
    length: float = 0.0
    width: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.shape, str) or not self.shape.strip():
            raise ValueError("ImpactAreaSpec.shape 必须是非空字符串")
        if (
            isinstance(self.radius, bool)
            or not isinstance(self.radius, int | float)
            or self.radius < 0
        ):
            raise ValueError("ImpactAreaSpec.radius 必须为非负数")
        if not isinstance(self.local_offset_xz, Vector3):
            raise ValueError("ImpactAreaSpec.local_offset_xz 必须是 Vector3")
        for value, name in ((self.length, "length"), (self.width, "width")):
            if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
                raise ValueError(f"ImpactAreaSpec.{name} 必须为非负数")
        if self.shape == "攻击盒" and (self.length <= 0 or self.width <= 0):
            raise ValueError("ImpactAreaSpec 形状为攻击盒时 length 与 width 必须为正数")

    def resolve(
        self,
        anchor_position: Vector3,
        attack_direction: Vector3,
    ) -> CircleArea | OrientedBoxArea:
        """把规格投影到锚点位置，得到可查询的具体范围。

        本地偏移先随攻击方向旋转到世界系，再叠加到锚点位置：球与圆柱投影为
        同半径 Circle（高度忽略），攻击盒投影为朝向攻击方向的 OrientedBox。
        ``attack_direction`` 只取 X/Z 分量并归一化，零向量报错。
        """

        forward_x, forward_z = _attack_frame(attack_direction)
        rotated_offset = _offset_in_attack_frame(self.local_offset_xz, forward_x, forward_z)
        center = Vector3(
            x=anchor_position.x + rotated_offset.x,
            y=anchor_position.y + self.local_offset_xz.y,
            z=anchor_position.z + rotated_offset.z,
        )
        if self.shape == "攻击盒":
            return OrientedBoxArea(
                center=center,
                facing=Vector3(x=forward_x, y=0.0, z=forward_z),
                length=self.length,
                width=self.width,
            )
        if self.shape not in {"球", "圆", "圆柱"}:
            raise ValueError(f"未支持的伤害 AOE 形状：{self.shape}")
        return CircleArea(center=center, radius=self.radius)


def _attack_frame(direction: Vector3) -> tuple[float, float]:
    """返回攻击方向的 X/Z 归一化基向量 ``(forward_x, forward_z)``。"""

    length = hypot(direction.x, direction.z)
    if length == 0.0:
        raise ValueError("攻击方向在 X/Z 平面不能为零向量")
    return direction.x / length, direction.z / length


def _offset_in_attack_frame(offset: Vector3, forward_x: float, forward_z: float) -> Vector3:
    """把攻击方向本地系下的偏移旋转到世界系（Y 轴分量不参与旋转）。

    本地系基向量与 ``OrientedBoxArea.contains`` 一致：forward 为攻击方向单位
    向量，right 为其垂直基 ``(-forward_z, forward_x)``，保证偏移与盒体共用同一
    朝向框架。
    """

    right_x = -forward_z
    right_z = forward_x
    return Vector3(
        x=offset.x * right_x + offset.z * forward_x,
        y=offset.y,
        z=offset.x * right_z + offset.z * forward_z,
    )
