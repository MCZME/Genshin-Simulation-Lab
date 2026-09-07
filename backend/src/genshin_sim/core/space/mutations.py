from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.space.entities import SpatialEntity


def _validate_frame(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name}必须是非负整数")


def _validate_operation_id(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("空间实体 operation_id 必须是非空字符串")


@dataclass(frozen=True, slots=True)
class SpaceEntityMutationPlan:
    """只支持实体创建与删除的可预校验 Space 变更计划。"""

    operation_id: str
    frame: int
    expected_entity_version: int
    creations: tuple[SpatialEntity, ...] = ()
    removals: tuple[SpatialEntity, ...] = ()

    def __post_init__(self) -> None:
        _validate_operation_id(self.operation_id)
        _validate_frame(self.frame, "空间实体计划 frame")
        _validate_frame(self.expected_entity_version, "空间实体计划 expected_entity_version")
        if any(not isinstance(entity, SpatialEntity) for entity in self.creations):
            raise TypeError("空间实体创建项必须全部是 SpatialEntity")
        if any(not isinstance(entity, SpatialEntity) for entity in self.removals):
            raise TypeError("空间实体删除项必须全部是 SpatialEntity")

        creations = tuple(sorted(self.creations, key=lambda entity: entity.entity_id))
        removals = tuple(sorted(self.removals, key=lambda entity: entity.entity_id))
        creation_ids = tuple(entity.entity_id for entity in creations)
        removal_ids = tuple(entity.entity_id for entity in removals)
        if len(creation_ids) != len(set(creation_ids)):
            raise ValueError("空间实体计划包含重复创建 id")
        if len(removal_ids) != len(set(removal_ids)):
            raise ValueError("空间实体计划包含重复删除 id")
        if set(creation_ids) & set(removal_ids):
            raise ValueError("同一空间实体 id 不能同时创建和删除")
        object.__setattr__(self, "creations", creations)
        object.__setattr__(self, "removals", removals)

    @property
    def is_empty(self) -> bool:
        return not self.creations and not self.removals


@dataclass(frozen=True, slots=True)
class SpaceEntityCommitReceipt:
    """已经提交的 Space 实体计划及其最终版本。"""

    plan: SpaceEntityMutationPlan
    entity_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.plan, SpaceEntityMutationPlan):
            raise TypeError("空间实体提交回执必须引用 SpaceEntityMutationPlan")
        _validate_frame(self.entity_version, "空间实体提交回执 entity_version")
