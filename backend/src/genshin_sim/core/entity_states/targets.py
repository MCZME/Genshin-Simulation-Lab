from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


@dataclass(slots=True)
class TargetRuntimeState:
    """单个目标的最小运行态。

    空间位置由 `Space` 中的 `target:*` 空间实体保存；这里仅保存目标战斗身份和
    来自场景配置的最小战斗参数。
    """

    target_id: str
    level: int | None = None
    resistance: Mapping[str, object] = field(default_factory=dict)
    spatial_entity_id: str = ""

    def __post_init__(self) -> None:
        if not self.target_id:
            msg = "目标 id 必须是非空字符串"
            raise ValueError(msg)
        if self.level is not None and self.level <= 0:
            msg = "目标等级必须是正整数"
            raise ValueError(msg)

        resistance = dict(self.resistance)
        for resistance_key in resistance:
            if not resistance_key:
                msg = "目标抗性名称必须是非空字符串"
                raise ValueError(msg)
        self.resistance = resistance

        if not self.spatial_entity_id:
            self.spatial_entity_id = f"target:{self.target_id}"
        if not self.spatial_entity_id.strip():
            msg = "目标空间实体 id 必须是非空字符串"
            raise ValueError(msg)


class TargetRuntimeCollection:
    """多个目标运行态的只读索引容器。"""

    __slots__ = ("_targets_by_id", "_targets_by_spatial_entity_id")

    def __init__(self, targets: Iterable[TargetRuntimeState] = ()) -> None:
        targets_by_id: dict[str, TargetRuntimeState] = {}
        targets_by_spatial_entity_id: dict[str, TargetRuntimeState] = {}

        for target in targets:
            if target.target_id in targets_by_id:
                msg = f"目标 id 重复：{target.target_id}"
                raise ValueError(msg)
            if target.spatial_entity_id in targets_by_spatial_entity_id:
                msg = f"目标空间实体 id 重复：{target.spatial_entity_id}"
                raise ValueError(msg)
            targets_by_id[target.target_id] = target
            targets_by_spatial_entity_id[target.spatial_entity_id] = target

        self._targets_by_id = targets_by_id
        self._targets_by_spatial_entity_id = targets_by_spatial_entity_id

    @property
    def targets(self) -> tuple[TargetRuntimeState, ...]:
        return tuple(self._targets_by_id.values())

    @property
    def target_ids(self) -> tuple[str, ...]:
        return tuple(self._targets_by_id)

    def get(self, target_id: str) -> TargetRuntimeState | None:
        return self._targets_by_id.get(target_id)

    def get_by_spatial_entity_id(self, spatial_entity_id: str) -> TargetRuntimeState | None:
        return self._targets_by_spatial_entity_id.get(spatial_entity_id)

    def __len__(self) -> int:
        return len(self._targets_by_id)
