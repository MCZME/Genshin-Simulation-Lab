"""generic 下落攻击数据（全角色统一/法器通用）。

低空/高空阈值是跨角色统一的临时数据，统一资料确认后替换；攻击数据（形状、
区域、偏移、攻击标签、元素量）按武器类型通用资料表维护，当前为法器通用
数据。垂直运动由 ``core/systems/movement`` 统一推进。
"""

from __future__ import annotations

from genshin_sim.core.space.geometry import Vector3

# 临时数据（待统一资料确认后替换）
PLUNGE_LOW_AIR_HEIGHT = 1.5
PLUNGE_HIGH_AIR_HEIGHT = 2.0

# 法器通用下落攻击资料（已确认，来源为通用攻击数据表）
PLUNGE_MAIN_ATTACK_TAG = "下落攻击"
PLUNGE_COLLISION_AOE_SHAPE = "球"
PLUNGE_COLLISION_AOE_RADIUS = 1.5
PLUNGE_COLLISION_AOE_OFFSET = Vector3(0.0, 0.0, 0.0)
PLUNGE_COLLISION_ELEMENTAL_AMOUNT = 0
PLUNGE_LANDING_AOE_SHAPE = "圆柱"
PLUNGE_LANDING_AOE_OFFSET = Vector3(0.0, -0.5, 0.0)
PLUNGE_LANDING_LOW_AOE_RADIUS = 3.0
PLUNGE_LANDING_HIGH_AOE_RADIUS = 3.5
PLUNGE_LANDING_ELEMENTAL_AMOUNT = 1
