from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from genshin_sim.core.actions import ActionOwnerRef, CandidateTargetRef


class ImpactKind(StrEnum):
    """动作或运行态实体发起的机制请求类型。"""

    DAMAGE = "damage"
    HEAL = "heal"
    APPLY_AURA = "apply_aura"
    APPLY_STATUS = "apply_status"
    CREATE_ENTITY = "create_entity"
    ENERGY = "energy"
    MOVEMENT = "movement"


@dataclass(frozen=True, slots=True)
class ImpactRequest:
    """一次待机制系统结算的通用影响请求。

    该模型只描述请求来源和结算意图，不直接计算伤害、治疗、附着或状态结果。
    """

    frame: int
    kind: ImpactKind
    impact_key: str
    owner_slot: int | None = None
    action_key: str | None = None
    request_id: str | None = None
    source_impact_point_id: str | None = None
    target_refs: tuple[str, ...] = ()
    scaling_ref: str | None = None
    element: str | None = None
    tags: tuple[str, ...] = ()
    params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.frame < 0:
            msg = "影响请求帧号不能为负数"
            raise ValueError(msg)
        if not self.impact_key.strip():
            msg = "impact_key 必须是非空字符串"
            raise ValueError(msg)
        if self.owner_slot is not None and self.owner_slot <= 0:
            msg = "owner_slot 必须是正整数"
            raise ValueError(msg)

        object.__setattr__(self, "target_refs", tuple(self.target_refs))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class ActionImpactContext:
    """ActionImpactPoint 到期后传给 content impact factory 的上下文。"""

    frame: int
    impact_point_id: str
    source_instance_id: int
    owner: ActionOwnerRef
    action_key: str
    impact_key: str
    target_refs: tuple[CandidateTargetRef, ...] = ()
    params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.frame < 0:
            msg = "动作影响上下文帧号不能为负数"
            raise ValueError(msg)
        if self.source_instance_id <= 0:
            msg = "source_instance_id 必须是正整数"
            raise ValueError(msg)
        if not self.impact_point_id.strip():
            msg = "impact_point_id 必须是非空字符串"
            raise ValueError(msg)
        if not self.action_key.strip():
            msg = "action_key 必须是非空字符串"
            raise ValueError(msg)
        if not self.impact_key.strip():
            msg = "impact_key 必须是非空字符串"
            raise ValueError(msg)
        object.__setattr__(self, "target_refs", tuple(self.target_refs))
        object.__setattr__(self, "params", dict(self.params))
