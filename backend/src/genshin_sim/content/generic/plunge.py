"""generic 下落攻击数据（全角色统一/按武器类型通用）。

低空/高空阈值是跨角色统一的临时数据，统一资料确认后替换；攻击数据（形状、
区域、偏移、攻击标签、打击类型、远近类型、元素量）按武器类型通用资料表
维护，键与角色资产 ``weapon_type`` 一致。削韧、冲击、停滞等维度不在当前
仿真范围。垂直运动由 ``core/movement`` 统一推进。
"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.space.geometry import Vector3

# 临时数据（待统一资料确认后替换）
PLUNGE_LOW_AIR_HEIGHT = 1.5
PLUNGE_HIGH_AIR_HEIGHT = 2.0


@dataclass(frozen=True, slots=True)
class PlungeCollisionData:
    """下坠期间（下落碰撞）命中数据。"""

    aoe_shape: str
    aoe_radius: float
    aoe_offset: Vector3
    elemental_amount: int
    strike_type: StrikeType
    range_type: str


@dataclass(frozen=True, slots=True)
class PlungeLandingData:
    """坠地冲击命中数据（低空/高空两个半径）。"""

    aoe_shape: str
    aoe_offset: Vector3
    low_aoe_radius: float
    high_aoe_radius: float
    elemental_amount: int
    strike_type: StrikeType
    range_type: str


@dataclass(frozen=True, slots=True)
class PlungeWeaponAttackData:
    """单个武器类型的通用下落攻击资料。"""

    main_attack_tag: str
    collision: PlungeCollisionData
    landing: PlungeLandingData


# 圆柱区域第二分量为高度、偏移 Y 分量由 X/Z 模型忽略（不参与查询）。
PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE: dict[str, PlungeWeaponAttackData] = {
    "sword": PlungeWeaponAttackData(
        main_attack_tag="下落攻击",
        collision=PlungeCollisionData(
            aoe_shape="球",
            aoe_radius=1.0,
            aoe_offset=Vector3(0.0, 0.0, 1.0),
            elemental_amount=0,
            strike_type=StrikeType.SLASH,
            range_type="近战",
        ),
        landing=PlungeLandingData(
            aoe_shape="圆柱",
            aoe_offset=Vector3(0.0, -0.5, 1.0),
            low_aoe_radius=3.0,
            high_aoe_radius=5.0,
            elemental_amount=1,
            strike_type=StrikeType.BLUNT,
            range_type="近战",
        ),
    ),
    "claymore": PlungeWeaponAttackData(
        main_attack_tag="下落攻击",
        collision=PlungeCollisionData(
            aoe_shape="球",
            aoe_radius=1.0,
            aoe_offset=Vector3(0.0, 0.0, 1.0),
            elemental_amount=0,
            strike_type=StrikeType.SLASH,
            range_type="近战",
        ),
        landing=PlungeLandingData(
            aoe_shape="圆柱",
            aoe_offset=Vector3(0.0, -0.5, 1.0),
            low_aoe_radius=3.0,
            high_aoe_radius=5.0,
            elemental_amount=1,
            strike_type=StrikeType.BLUNT,
            range_type="近战",
        ),
    ),
    "polearm": PlungeWeaponAttackData(
        main_attack_tag="下落攻击",
        collision=PlungeCollisionData(
            aoe_shape="球",
            aoe_radius=1.0,
            aoe_offset=Vector3(0.0, 0.0, 1.0),
            elemental_amount=0,
            strike_type=StrikeType.SLASH,
            range_type="近战",
        ),
        landing=PlungeLandingData(
            aoe_shape="圆柱",
            aoe_offset=Vector3(0.0, -0.5, 1.0),
            low_aoe_radius=3.0,
            high_aoe_radius=5.0,
            elemental_amount=1,
            strike_type=StrikeType.BLUNT,
            range_type="近战",
        ),
    ),
    "catalyst": PlungeWeaponAttackData(
        main_attack_tag="下落攻击",
        collision=PlungeCollisionData(
            aoe_shape="球",
            aoe_radius=1.5,
            aoe_offset=Vector3(0.0, 0.0, 0.0),
            elemental_amount=0,
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
        ),
        landing=PlungeLandingData(
            aoe_shape="圆柱",
            aoe_offset=Vector3(0.0, -0.5, 0.0),
            low_aoe_radius=3.0,
            high_aoe_radius=3.5,
            elemental_amount=1,
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
        ),
    ),
    "bow": PlungeWeaponAttackData(
        main_attack_tag="下落攻击",
        collision=PlungeCollisionData(
            aoe_shape="球",
            aoe_radius=1.0,
            aoe_offset=Vector3(0.0, 0.0, 0.0),
            elemental_amount=0,
            strike_type=StrikeType.PIERCE,
            range_type="近战",
        ),
        landing=PlungeLandingData(
            aoe_shape="圆柱",
            aoe_offset=Vector3(0.0, -0.5, 0.0),
            low_aoe_radius=3.0,
            high_aoe_radius=3.5,
            elemental_amount=1,
            strike_type=StrikeType.PIERCE,
            range_type="近战",
        ),
    ),
}
