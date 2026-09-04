from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import TYPE_CHECKING

from genshin_sim.core.space.entities import SpatialEntity, SpatialEntityKind
from genshin_sim.core.space.errors import SpaceEntityPlanConflictError
from genshin_sim.core.space.geometry import CircleArea, CircleSectorArea, OrientedBoxArea, Vector3
from genshin_sim.core.space.mutations import SpaceEntityCommitReceipt, SpaceEntityMutationPlan
from genshin_sim.core.space.snapshots import SpaceSnapshot

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext

ACTIVE_CHARACTER_ENTITY_ID = "player:active"


class Space:
    """战场空间的最小查询容器。

    当前不模拟移动、碰撞或实体挤压，只提供空间实体登记和 X/Z 平面范围查询。
    """

    def __init__(self, entities: Iterable[SpatialEntity] = ()) -> None:
        self._entities: dict[str, SpatialEntity] = {}
        self._current_frame = 0
        self._entity_version = 0
        self._committed_entity_operations: dict[str, SpaceEntityCommitReceipt] = {}
        self._external_write_guard: Callable[[], bool] | None = None
        self._fact_publication_active = False
        for entity in entities:
            self.add_entity(entity)

    @property
    def entities(self) -> tuple[SpatialEntity, ...]:
        return tuple(self._entities.values())

    @property
    def current_frame(self) -> int:
        return self._current_frame

    @property
    def entity_version(self) -> int:
        return self._entity_version

    def add_entity(self, entity: SpatialEntity) -> SpatialEntity:
        self._ensure_external_write_allowed()
        if entity.entity_id in self._entities:
            msg = f"空间实体 id 重复：{entity.entity_id}"
            raise ValueError(msg)
        self._entities[entity.entity_id] = entity
        self._entity_version += 1
        return entity

    def update_entity(self, entity: SpatialEntity) -> SpatialEntity:
        self._ensure_external_write_allowed()
        if entity.entity_id not in self._entities:
            msg = f"未知空间实体 id：{entity.entity_id}"
            raise KeyError(msg)
        if self._entities[entity.entity_id] == entity:
            return entity
        self._entities[entity.entity_id] = entity
        self._entity_version += 1
        return entity

    def remove_entity(self, entity_id: str) -> SpatialEntity:
        self._ensure_external_write_allowed()
        try:
            entity = self._entities.pop(entity_id)
        except KeyError as exc:
            msg = f"未知空间实体 id：{entity_id}"
            raise KeyError(msg) from exc
        self._entity_version += 1
        return entity

    def get_entity(self, entity_id: str) -> SpatialEntity | None:
        return self._entities.get(entity_id)

    def begin_entity_mutation(
        self,
        *,
        operation_id: str,
        frame: int,
    ) -> SpaceEntityMutationPlanner:
        return SpaceEntityMutationPlanner(self, operation_id=operation_id, frame=frame)

    def validate_entity_plan(
        self,
        plan: SpaceEntityMutationPlan,
    ) -> SpaceEntityCommitReceipt | None:
        if not isinstance(plan, SpaceEntityMutationPlan):
            raise TypeError("Space 实体计划必须是 SpaceEntityMutationPlan")
        committed = self._committed_entity_operations.get(plan.operation_id)
        if committed is not None:
            if committed.plan == plan:
                return committed
            raise SpaceEntityPlanConflictError("相同空间实体 operation_id 对应不同计划")
        if plan.frame != self._current_frame:
            raise SpaceEntityPlanConflictError("空间实体计划 frame 与当前 Space frame 不一致")
        if plan.expected_entity_version != self._entity_version:
            raise SpaceEntityPlanConflictError("空间实体变更计划已经过期")
        for entity in plan.creations:
            if entity.entity_id in self._entities:
                raise SpaceEntityPlanConflictError("空间实体创建 id 已存在")
        for entity in plan.removals:
            if self._entities.get(entity.entity_id) != entity:
                raise SpaceEntityPlanConflictError("空间实体删除前值冲突")
        return None

    def commit_prevalidated_entity_plan(
        self,
        plan: SpaceEntityMutationPlan,
    ) -> SpaceEntityCommitReceipt:
        self._ensure_external_write_allowed()
        committed = self.validate_entity_plan(plan)
        if committed is not None:
            return committed

        next_entities = dict(self._entities)
        for entity in plan.removals:
            del next_entities[entity.entity_id]
        for entity in plan.creations:
            next_entities[entity.entity_id] = entity
        if not plan.is_empty:
            self._entities = next_entities
            self._entity_version += 1
        receipt = SpaceEntityCommitReceipt(plan, self._entity_version)
        self._committed_entity_operations[plan.operation_id] = receipt
        return receipt

    def snapshot(self, frame: int) -> SpaceSnapshot:
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError("Space snapshot frame 必须是非负整数")
        return SpaceSnapshot(frame, self._entity_version, self.entities)

    def set_external_write_guard(self, guard: Callable[[], bool] | None) -> None:
        self._external_write_guard = guard

    @contextmanager
    def event_publication_guard(self) -> Iterator[None]:
        """禁止事实订阅者同步改写当前 Space Store。"""

        if self._fact_publication_active:
            raise SpaceEntityPlanConflictError("Space 领域事实发布不允许嵌套")
        self._fact_publication_active = True
        try:
            yield
        finally:
            self._fact_publication_active = False

    def update_active_character_slot(
        self,
        active_slot: int,
        *,
        entity_id: str = ACTIVE_CHARACTER_ENTITY_ID,
    ) -> SpatialEntity:
        entity = self._entities.get(entity_id)
        if entity is None:
            msg = f"未知空间实体 id：{entity_id}"
            raise KeyError(msg)
        if entity.kind is not SpatialEntityKind.ACTIVE_CHARACTER:
            msg = f"空间实体不是当前场上角色：{entity_id}"
            raise ValueError(msg)
        return self.update_entity(replace(entity, active_slot=active_slot))

    def entities_in_radius(
        self,
        center: Vector3,
        radius: float,
        *,
        kinds: Iterable[SpatialEntityKind] | None = None,
        exclude_entity_ids: Iterable[str] = (),
    ) -> tuple[SpatialEntity, ...]:
        area = CircleArea(center=center, radius=radius)
        return self.entities_in_area(
            area,
            kinds=kinds,
            exclude_entity_ids=exclude_entity_ids,
        )

    def entities_in_area(
        self,
        area: CircleArea | CircleSectorArea | OrientedBoxArea,
        *,
        kinds: Iterable[SpatialEntityKind] | None = None,
        exclude_entity_ids: Iterable[str] = (),
    ) -> tuple[SpatialEntity, ...]:
        kind_filter = None if kinds is None else frozenset(kinds)
        excluded = frozenset(exclude_entity_ids)
        return tuple(
            entity
            for entity in self._entities.values()
            if entity.entity_id not in excluded
            and entity.is_active_at(self._current_frame)
            and (kind_filter is None or entity.kind in kind_filter)
            and area.contains(entity.position)
        )

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        del context
        if frame < 0:
            msg = "帧号不能为负数"
            raise ValueError(msg)
        self._current_frame = frame

    def is_idle(self) -> bool:
        return True

    def _ensure_external_write_allowed(self) -> None:
        if self._fact_publication_active or (
            self._external_write_guard is not None and self._external_write_guard()
        ):
            raise SpaceEntityPlanConflictError("Space 写保护期间不允许修改空间实体")


class SpaceEntityMutationPlanner:
    """在工作投影中累积 Space 创建和删除，再封存为不可变计划。"""

    def __init__(self, space: Space, *, operation_id: str, frame: int) -> None:
        if frame != space.current_frame:
            raise SpaceEntityPlanConflictError("空间实体计划 frame 与当前 Space frame 不一致")
        self._space = space
        self._operation_id = operation_id
        self._frame = frame
        self._working_entities = dict(space._entities)
        self._creations: dict[str, SpatialEntity] = {}
        self._removals: dict[str, SpatialEntity] = {}
        self._sealed = False

    def create(self, entity: SpatialEntity) -> SpatialEntity:
        self._ensure_unsealed()
        if entity.entity_id in self._working_entities:
            raise SpaceEntityPlanConflictError("空间实体创建 id 已存在")
        self._working_entities[entity.entity_id] = entity
        self._creations[entity.entity_id] = entity
        return entity

    def remove(self, entity_id: str) -> SpatialEntity:
        self._ensure_unsealed()
        if entity_id in self._creations:
            raise SpaceEntityPlanConflictError("同一空间实体 id 不能同时创建和删除")
        try:
            entity = self._working_entities.pop(entity_id)
        except KeyError as exc:
            msg = f"未知空间实体 id：{entity_id}"
            raise KeyError(msg) from exc
        self._removals[entity_id] = entity
        return entity

    def cancel_create(self, entity_id: str) -> None:
        """撤销本批次尚未提交的创建项，供跨领域投影冲突时回退。"""

        self._ensure_unsealed()
        entity = self._creations.pop(entity_id, None)
        if entity is None:
            raise SpaceEntityPlanConflictError("空间实体创建项不存在，无法取消")
        self._working_entities.pop(entity_id, None)

    def seal(self) -> SpaceEntityMutationPlan:
        self._ensure_unsealed()
        self._sealed = True
        return SpaceEntityMutationPlan(
            operation_id=self._operation_id,
            frame=self._frame,
            expected_entity_version=self._space.entity_version,
            creations=tuple(self._creations.values()),
            removals=tuple(self._removals.values()),
        )

    def _ensure_unsealed(self) -> None:
        if self._sealed:
            raise SpaceEntityPlanConflictError("空间实体计划已经封存")
