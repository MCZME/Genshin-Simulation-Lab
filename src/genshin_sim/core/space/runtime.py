from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from genshin_sim.core.actions.manager import (
    TEAM_SWITCH_ACTION_KEY,
    TEAM_SWITCH_TARGET_SLOT_PARAM,
    ActionInstance,
    ActionManager,
    CandidateTargetRef,
)
from genshin_sim.core.entity_states import TargetRuntimeCollection
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.simulation.team import TeamRuntimeState, TeamSwitchResult
from genshin_sim.core.space.created_objects import CreatedObjectRuntime
from genshin_sim.core.space.entities import SpatialEntity, SpatialEntityKind
from genshin_sim.core.space.geometry import CircleArea, Vector3
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID, Space

if TYPE_CHECKING:
    from genshin_sim.core.simulation.context import SimulationContext


@dataclass(frozen=True, slots=True)
class SpaceActionConsumptionResult:
    """空间动作消费器返回的通用结果。"""

    status: str
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.status.strip():
            msg = "空间动作消费状态必须是非空字符串"
            raise ValueError(msg)
        object.__setattr__(self, "payload", dict(self.payload))


class SpaceActionConsumer(Protocol):
    """空间实体动作消费器协议。"""

    @property
    def consumer_key(self) -> str:
        """消费器标识。"""
        ...

    def consume(
        self,
        context: SimulationContext,
        space_runtime: SpaceRuntime,
        instance: ActionInstance,
        frame: int,
    ) -> SpaceActionConsumptionResult:
        """消费一个已调度的动作实例。"""
        ...


class SwitchAcceptedCallback(Protocol):
    """切人成功后的输入会话清理回调。"""

    def __call__(self, slot: int, *, reason: str) -> None:
        """清理指定槽位的待定输入会话。"""
        ...


class SpaceRuntime(FrameUpdatable):
    """战场空间运行态拥有者与空间实体动作消费协调器。"""

    def __init__(
        self,
        *,
        space: Space | None = None,
        team_state: TeamRuntimeState,
        targets: TargetRuntimeCollection | None = None,
        created_object_runtime: CreatedObjectRuntime | None = None,
        action_manager: ActionManager,
        consumers: Mapping[tuple[str, str], SpaceActionConsumer] | None = None,
    ) -> None:
        self.space = space or Space()
        self.team_state = team_state
        self.targets = targets or TargetRuntimeCollection()
        self.created_object_runtime = created_object_runtime or CreatedObjectRuntime()
        self.action_manager = action_manager
        self._consumers: dict[tuple[str, str], SpaceActionConsumer] = {}
        self._consumed_instance_ids: set[int] = set()
        self._current_frame = 0

        if consumers is not None:
            for (actor_entity_id, action_key), consumer in consumers.items():
                self.register_consumer(actor_entity_id, action_key, consumer)

    @property
    def entities(self) -> tuple[SpatialEntity, ...]:
        return self.space.entities

    @property
    def consumed_instance_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._consumed_instance_ids))

    @property
    def consumer_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._consumers)

    def register_consumer(
        self,
        actor_entity_id: str,
        action_key: str,
        consumer: SpaceActionConsumer,
    ) -> None:
        _validate_non_empty_text(actor_entity_id, "空间动作 actor_entity_id")
        _validate_non_empty_text(action_key, "空间动作 action_key")
        key = (actor_entity_id, action_key)
        if key in self._consumers:
            msg = f"空间动作消费器重复：{actor_entity_id} / {action_key}"
            raise ValueError(msg)
        self._consumers[key] = consumer

    def add_entity(self, entity: SpatialEntity) -> SpatialEntity:
        return self.space.add_entity(entity)

    def update_entity(self, entity: SpatialEntity) -> SpatialEntity:
        return self.space.update_entity(entity)

    def get_entity(self, entity_id: str) -> SpatialEntity | None:
        return self.space.get_entity(entity_id)

    def update_active_character_slot(self, active_slot: int) -> SpatialEntity:
        return self.space.update_active_character_slot(active_slot)

    def entities_in_radius(
        self,
        center: Vector3,
        radius: float,
        *,
        kinds: Iterable[SpatialEntityKind] | None = None,
        exclude_entity_ids: Iterable[str] = (),
    ) -> tuple[SpatialEntity, ...]:
        return self.space.entities_in_radius(
            center,
            radius,
            kinds=kinds,
            exclude_entity_ids=exclude_entity_ids,
        )

    def entities_in_area(
        self,
        area: CircleArea,
        *,
        kinds: Iterable[SpatialEntityKind] | None = None,
        exclude_entity_ids: Iterable[str] = (),
    ) -> tuple[SpatialEntity, ...]:
        return self.space.entities_in_area(
            area,
            kinds=kinds,
            exclude_entity_ids=exclude_entity_ids,
        )

    def resolve_candidate_targets(
        self,
        candidate_entity_ids: tuple[str, ...],
    ) -> tuple[CandidateTargetRef, ...]:
        return tuple(
            CandidateTargetRef(
                spatial_entity_id=entity_id,
                target_id=target.target_id,
            )
            for entity_id in candidate_entity_ids
            if (target := self.targets.get_by_spatial_entity_id(entity_id)) is not None
        )

    def sync_created_objects_to_space(self) -> None:
        for state in self.created_object_runtime.objects:
            self.sync_entity_to_space(state.entity)

    def sync_entity_to_space(self, entity: SpatialEntity) -> None:
        if self.space.get_entity(entity.entity_id) is None:
            self.space.add_entity(entity)
            return
        self.space.update_entity(entity)

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        if frame < 0:
            msg = "帧号不能为负数"
            raise ValueError(msg)
        self._current_frame = frame
        self.space.update_frame(context, frame)
        self._consume_action_instances(context, frame)

    def is_idle(self) -> bool:
        actions_idle = all(
            instance.start_frame > self._current_frame
            or instance.instance_id in self._consumed_instance_ids
            or instance.actor_entity_id is None
            or (instance.actor_entity_id, instance.action_key) not in self._consumers
            for instance in self.action_manager.instances
        )
        return actions_idle and self.created_object_runtime.is_idle()

    def _consume_action_instances(self, context: SimulationContext, frame: int) -> None:
        for instance in self.action_manager.instances:
            if instance.instance_id in self._consumed_instance_ids:
                continue
            if instance.start_frame > frame:
                continue
            if instance.actor_entity_id is None:
                continue
            consumer = self._consumers.get((instance.actor_entity_id, instance.action_key))
            if consumer is None:
                continue

            result = consumer.consume(context, self, instance, frame)
            self._consumed_instance_ids.add(instance.instance_id)
            self.action_manager.record_consumption(
                frame=frame,
                instance_id=instance.instance_id,
                consumer_key=consumer.consumer_key,
                status=result.status,
                payload=result.payload,
            )


class TeamSwitchActionConsumer:
    """消费 player:active 上的 team.switch 动作实例。"""

    consumer_key = "space.team_switch"

    def __init__(
        self,
        *,
        on_switch_accepted: SwitchAcceptedCallback | None = None,
    ) -> None:
        self._on_switch_accepted = on_switch_accepted
        self._results: list[TeamSwitchResult] = []

    @property
    def results(self) -> tuple[TeamSwitchResult, ...]:
        return tuple(self._results)

    def consume(
        self,
        context: SimulationContext,
        space_runtime: SpaceRuntime,
        instance: ActionInstance,
        frame: int,
    ) -> SpaceActionConsumptionResult:
        del context
        if instance.action_key != TEAM_SWITCH_ACTION_KEY:
            msg = f"TeamSwitchActionConsumer 不支持动作：{instance.action_key}"
            raise ValueError(msg)
        target_slot = _target_slot_from_instance(instance)
        previous_slot = space_runtime.team_state.active_slot
        result = space_runtime.team_state.switch_to(target_slot, frame)
        self._results.append(result)

        if result.accepted:
            if space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID) is not None:
                space_runtime.update_active_character_slot(result.active_slot)
            if self._on_switch_accepted is not None:
                self._on_switch_accepted(previous_slot, reason="character_switch")

        return SpaceActionConsumptionResult(
            status=result.status.value,
            payload={
                "requested_slot": result.requested_slot,
                "previous_slot": result.previous_slot,
                "active_slot": result.active_slot,
            },
        )


def _target_slot_from_instance(instance: ActionInstance) -> int:
    value = instance.params.get(TEAM_SWITCH_TARGET_SLOT_PARAM)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{TEAM_SWITCH_ACTION_KEY}.params.{TEAM_SWITCH_TARGET_SLOT_PARAM} 必须是整数"
        raise ValueError(msg)
    return value


def _validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name}必须是非空字符串"
        raise ValueError(msg)
