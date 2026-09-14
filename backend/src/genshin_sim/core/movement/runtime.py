"""Movement 位移设施运行时：垂直重力推进、起跳、落地与碰撞事实。

本模块唯一拥有实体的垂直运动状态；每帧对空中实体施加重力并同步 `Space`
位置。自然下落从速度 0 开始；起跳由外部意图入口 `start_jump` 置入向上的
初速度；落地时 Y 归零并发布事实。

本设施以项目自身的垂直运动模型为基准，不承载原神跳跃规则：起跳初速度由
调用方给出，原神侧的跳跃高度、体力与坠落伤害不属于本模块。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace

from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.events.payloads import (
    MovementCollidedPayload,
    MovementLandedPayload,
)
from genshin_sim.core.movement.enums import MovementFact
from genshin_sim.core.movement.models import (
    MovementCollisionRecord,
    MovementLandRecord,
    VerticalMotionState,
)
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.space import SpatialEntityKind, Vector3

# 临时统一重力（m/frame^2 的每帧等效值按 60fps 折算），待统一资料确认。
GRAVITY = 9.8


class MovementRuntimeError(RuntimeError):
    """Movement 运行期错误。"""


class MovementRuntime(FrameUpdatable):
    """垂直运动运行态：重力推进、落地/碰撞事实与 Space 同步。"""

    def __init__(self, *, gravity: float = GRAVITY) -> None:
        if (
            isinstance(gravity, bool)
            or not isinstance(gravity, int | float)
            or not math.isfinite(gravity)
            or gravity <= 0
        ):
            msg = "gravity 必须是正有限数"
            raise ValueError(msg)
        self.gravity = gravity
        self._motions: dict[str, VerticalMotionState] = {}
        self._frame_facts: dict[int, dict[str, frozenset[MovementFact]]] = {}
        self._current_frame = 0
        self._landed_records: list[MovementLandRecord] = []
        self._collision_records: list[MovementCollisionRecord] = []

    @property
    def motions(self) -> tuple[VerticalMotionState, ...]:
        return tuple(self._motions.values())

    @property
    def landed_records(self) -> tuple[MovementLandRecord, ...]:
        return tuple(self._landed_records)

    @property
    def collision_records(self) -> tuple[MovementCollisionRecord, ...]:
        return tuple(self._collision_records)

    def update_frame(self, context, frame: int) -> None:
        if frame < 0:
            msg = "帧号不能为负数"
            raise ValueError(msg)
        if frame <= self._current_frame:
            msg = "Movement 帧不能重复推进"
            raise MovementRuntimeError(msg)
        self._current_frame = frame
        self._frame_facts = {key: value for key, value in self._frame_facts.items() if key >= frame}
        self._frame_facts[frame] = {}
        if context.space_runtime is not None:
            self._track_airborne(context, frame)
            for entity_id, motion in tuple(self._motions.items()):
                self._advance(context, frame, entity_id, motion)

    def facts_for(self, entity_id: str, frame: int) -> frozenset[MovementFact]:
        """返回实体在指定帧推进后的事实集合（事件驱动消费入口）。"""

        return self._frame_facts.get(frame, {}).get(entity_id, frozenset())

    def set_velocity(self, entity_id: str, velocity_y: float, *, frame: int | None = None) -> None:
        """为实体设置垂直速度（跳跃、击飞等未来意图的入口）。"""

        if (
            isinstance(velocity_y, bool)
            or not isinstance(velocity_y, int | float)
            or not math.isfinite(velocity_y)
        ):
            raise MovementRuntimeError("vertical_velocity 必须是有限数字")
        if entity_id in self._motions:
            motion = self._motions[entity_id]
            self._motions[entity_id] = replace(motion, velocity_y=float(velocity_y))
            return
        raise MovementRuntimeError(f"实体 {entity_id} 尚未进入下落状态，无法设置垂直速度")

    def start_jump(
        self,
        context,
        entity_id: str,
        upward_velocity: float,
        *,
        frame: int,
    ) -> None:
        """让实体起跳：置入向上初速度并进入上升的垂直运动状态。

        起跳是外部意图（跳跃动作、击飞等）而非重力推进的结果，因此不走
        ``_track_airborne``；``upward_velocity`` 必须由调用方给出（正数，
        单位与 ``GRAVITY`` 一致），Movement 不内置任何角色跳跃数值。
        已处于垂直运动中的实体不允许再次起跳：跳跃次数模型尚未来源化。
        """

        if not isinstance(entity_id, str) or not entity_id.strip():
            raise MovementRuntimeError("entity_id 必须是非空字符串")
        if (
            isinstance(upward_velocity, bool)
            or not isinstance(upward_velocity, int | float)
            or not math.isfinite(upward_velocity)
        ):
            raise MovementRuntimeError("upward_velocity 必须是有限数字")
        if upward_velocity <= 0:
            raise MovementRuntimeError("upward_velocity 必须是正数")
        if frame < 0:
            raise MovementRuntimeError("帧号不能为负数")
        if entity_id in self._motions:
            raise MovementRuntimeError(f"实体 {entity_id} 已在垂直运动中，不能再次起跳")
        base_height = 0.0
        if context.space_runtime is None:
            raise MovementRuntimeError("起跳需要 space_runtime")
        entity = context.space_runtime.get_entity(entity_id)
        if entity is None:
            raise MovementRuntimeError(f"起跳实体不存在：{entity_id}")
        base_height = float(entity.position.y)
        # ``fall_start_*`` 记的是起跳点而非顶点：本设施尚未建模"上升转下落"的顶点，
        # 因此跳跃落地时 ``MovementLandRecord.fall_height`` 报的是起跳高度。接下落
        # 伤害或受击逻辑前需要补顶点跟踪，届时同步该口径。
        self._motions[entity_id] = VerticalMotionState(
            entity_id=entity_id,
            height=base_height,
            velocity_y=-float(upward_velocity),
            fall_start_frame=frame,
            fall_start_height=base_height,
        )

    def is_idle(self) -> bool:
        return not self._motions

    def _track_airborne(self, context, frame: int) -> None:
        for entity in context.space_runtime.entities:
            if entity.kind is not SpatialEntityKind.ACTIVE_CHARACTER:
                continue
            if entity.entity_id in self._motions:
                continue
            if entity.position.y <= 0:
                continue
            self._motions[entity.entity_id] = VerticalMotionState(
                entity_id=entity.entity_id,
                height=float(entity.position.y),
                velocity_y=0.0,
                fall_start_frame=frame,
                fall_start_height=float(entity.position.y),
            )

    def _advance(self, context, frame: int, entity_id: str, motion: VerticalMotionState) -> None:
        entity = context.space_runtime.get_entity(entity_id)
        if entity is None:
            self._motions.pop(entity_id, None)
            return
        velocity = motion.velocity_y + self.gravity / 60
        height = motion.height - velocity / 60
        facts = {MovementFact.FALLING}

        if not motion.collided and self._collides_with_target(
            context, entity, motion.height, height
        ):
            motion = replace(motion, collided=True)
            facts.add(MovementFact.COLLIDED)
            self._collision_records.append(
                MovementCollisionRecord(entity_id=entity_id, frame=frame)
            )
            with context.space_runtime.space.event_publication_guard():
                context.events.publish(
                    GameEvent(
                        EventType.MOVEMENT_COLLIDED,
                        frame=frame,
                        source=self,
                        payload=MovementCollidedPayload(entity_id=entity_id, frame=frame),
                    )
                )

        if height <= 0:
            context.space_runtime.apply_displacement(
                entity_id,
                Vector3(entity.position.x, 0.0, entity.position.z),
            )
            self._motions.pop(entity_id, None)
            facts.add(MovementFact.LANDED)
            self._landed_records.append(
                MovementLandRecord(
                    entity_id=entity_id,
                    frame=frame,
                    fall_start_frame=motion.fall_start_frame,
                    fall_height=motion.fall_start_height,
                )
            )
            with context.space_runtime.space.event_publication_guard():
                context.events.publish(
                    GameEvent(
                        EventType.MOVEMENT_LANDED,
                        frame=frame,
                        source=self,
                        payload=MovementLandedPayload(
                            entity_id=entity_id,
                            frame=frame,
                            fall_start_frame=motion.fall_start_frame,
                            fall_height=motion.fall_start_height,
                        ),
                    )
                )
        else:
            self._motions[entity_id] = replace(
                motion,
                height=height,
                velocity_y=velocity,
            )
            context.space_runtime.apply_displacement(
                entity_id,
                Vector3(entity.position.x, height, entity.position.z),
            )
        self._frame_facts[frame][entity_id] = frozenset(facts)

    def _collides_with_target(self, context, entity, old_height: float, height: float) -> bool:
        """下坠碰撞：角色碰撞箱与目标碰撞箱 X/Z 与 Y 区间重叠。

        ``old_height`` 是本帧推进前的基座高度，``height`` 是推进后的基座高度；
        使用扫掠区间避免高速下落时单帧位移直接穿过目标碰撞箱。
        """

        if height < 0 and old_height < 0:
            return False
        char_box = entity.collision_box
        char_bottom = height
        char_top = height + char_box.height
        old_bottom = old_height
        old_top = old_height + char_box.height
        for target in context.space_runtime.entities:
            if target.kind is not SpatialEntityKind.TARGET:
                continue
            target_radius = target.collision_box.radius
            distance = entity.position.distance_xz_to(target.position)
            if distance > char_box.radius + target_radius:
                continue
            target_bottom = target.position.y
            target_top = target_bottom + target.collision_box.height
            sweep_bottom = min(old_bottom, char_bottom)
            sweep_top = max(old_top, char_top)
            if sweep_bottom <= target_top and sweep_top >= target_bottom:
                return True
        return False


class MovementImpactRequestHandler:
    """把 MOVEMENT ImpactRequest 转交给 MovementRuntime。"""

    def __init__(self, runtime: MovementRuntime) -> None:
        self.runtime = runtime

    def has_movement_contract(self, request) -> bool:
        from genshin_sim.core.impacts import ImpactKind

        return request.kind is ImpactKind.MOVEMENT and isinstance(
            request.params.get("movement"),
            Mapping,
        )

    def handle(self, context, request) -> None:
        params = request.params["movement"]
        if not isinstance(params, Mapping):
            msg = "movement 参数必须是对象"
            raise MovementRuntimeError(msg)
        entity_id = params.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id.strip():
            msg = "movement.entity_id 必须是非空字符串"
            raise MovementRuntimeError(msg)
        velocity = params.get("vertical_velocity", 0.0)
        if isinstance(velocity, bool) or not isinstance(velocity, int | float):
            msg = "movement.vertical_velocity 必须是数字"
            raise MovementRuntimeError(msg)
        jump = params.get("jump")
        if jump is None:
            self.runtime.set_velocity(entity_id, float(velocity))
            return
        # 两种模式互斥按"参数是否出现"判定，而不是按取值是否为 0：显式传
        # ``vertical_velocity: 0`` 与 ``jump`` 同时出现时同样拒绝。
        if "vertical_velocity" in params:
            msg = "movement.jump 与 movement.vertical_velocity 不能同时使用"
            raise MovementRuntimeError(msg)
        if not isinstance(jump, Mapping):
            msg = "movement.jump 必须是对象"
            raise MovementRuntimeError(msg)
        upward = jump.get("upward_velocity")
        if isinstance(upward, bool) or not isinstance(upward, int | float):
            msg = "movement.jump.upward_velocity 必须是数字"
            raise MovementRuntimeError(msg)
        self.runtime.start_jump(
            context,
            entity_id,
            float(upward),
            frame=request.frame,
        )
