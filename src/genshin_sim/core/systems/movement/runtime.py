"""Movement 领域运行时：垂直重力推进、落地与碰撞事实。

MovementSystem 唯一拥有实体的垂直运动状态；每帧对空中实体施加重力并同步
`Space` 位置。自然下落从速度 0 开始；落地时 Y 归零并发布事实。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.events.payloads import (
    MovementCollidedPayload,
    MovementLandedPayload,
)
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.space import SpatialEntityKind, Vector3
from genshin_sim.core.systems.movement.enums import MovementFact
from genshin_sim.core.systems.movement.models import (
    MovementCollisionRecord,
    MovementLandRecord,
    VerticalMotionState,
)

# 临时统一重力（m/frame^2 的每帧等效值按 60fps 折算），待统一资料确认。
GRAVITY = 9.8


class MovementRuntimeError(RuntimeError):
    """Movement 领域运行期错误。"""


class MovementRuntime(FrameUpdatable):
    """垂直运动运行态：重力推进、落地/碰撞事实与 Space 同步。"""

    def __init__(self, *, gravity: float = GRAVITY) -> None:
        if isinstance(gravity, bool) or not isinstance(gravity, int | float) or gravity <= 0:
            raise ValueError("gravity 必须是正数")
        self.gravity = float(gravity)
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
        if frame < self._current_frame:
            msg = "Movement 帧不能回退"
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

        if isinstance(velocity_y, bool) or not isinstance(velocity_y, int | float):
            raise MovementRuntimeError("vertical_velocity 必须是数字")
        if entity_id in self._motions:
            motion = self._motions[entity_id]
            self._motions[entity_id] = replace(motion, velocity_y=float(velocity_y))
            return
        raise MovementRuntimeError(
            f"实体 {entity_id} 尚未进入下落状态，无法设置垂直速度"
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

        if not motion.collided and self._collides_with_target(context, entity, height):
            motion = replace(motion, collided=True)
            facts.add(MovementFact.COLLIDED)
            self._collision_records.append(
                MovementCollisionRecord(entity_id=entity_id, frame=frame)
            )
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

    def _collides_with_target(self, context, entity, height: float) -> bool:
        """下坠碰撞：角色碰撞箱与目标碰撞箱 X/Z 与 Y 区间重叠。"""

        if height < 0:
            return False
        char_box = entity.collision_box
        char_bottom = height
        char_top = height + char_box.height
        for target in context.space_runtime.entities:
            if target.kind is not SpatialEntityKind.TARGET:
                continue
            target_radius = target.collision_box.radius
            distance = entity.position.distance_xz_to(target.position)
            if distance > char_box.radius + target_radius:
                continue
            target_bottom = target.position.y
            target_top = target_bottom + target.collision_box.height
            if char_bottom <= target_top and char_top >= target_bottom:
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
        del context
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
        self.runtime.set_velocity(entity_id, float(velocity))
