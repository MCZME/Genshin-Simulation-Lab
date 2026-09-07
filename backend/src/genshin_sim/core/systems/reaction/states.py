"""ReactionState 的强类型存储、计划和快照基础。"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from genshin_sim.core.elements import (
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
)
from genshin_sim.core.space import Vector3
from genshin_sim.core.systems.reaction.frozen_constants import (
    MIN_FREEZE_DECAY_RATE,
)

if TYPE_CHECKING:
    from genshin_sim.core.systems.reaction.models import (
        CapturedCrystallizeShieldBasis,
        CapturedTransformativeScalingBasis,
        CrystallizeShardStateCreationIntent,
        DendroCoreStateCreationIntent,
        DynamicTransformativeScalingBasis,
        LunarStormCloudStatePlanningIntent,
    )


def _frame(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} 必须是非负整数")


class ReactionStateSlot(StrEnum):
    FROZEN = "frozen"
    FREEZE_RECOVERY = "freeze_recovery"
    ELECTRO_CHARGED = "electro_charged"
    BURNING = "burning"
    QUICKEN = "quicken"
    CRYSTALLIZE_SHARD = "crystallize_shard"
    DENDRO_CORE = "dendro_core"
    LUNAR_STORM_CLOUD = "lunar_storm_cloud"
    LUNAR_CAGE = "lunar_cage"
    LUNAR_CRYSTALLIZE_ACCUMULATOR = "lunar_crystallize_accumulator"
    SPRAWLING_SHOT = "sprawling_shot"


class ScheduledStateTickKind(StrEnum):
    """由 ReactionState 物化的周期性工作种类。"""

    ELECTRO_CHARGED_PULSE = "electro_charged_pulse"
    BURNING_DAMAGE = "burning_damage"
    BURNING_PYRO_APPLICATION = "burning_pyro_application"
    LUNAR_STORM_CLOUD_ATTACK = "lunar_storm_cloud_attack"


class CrystallizeShardLifecycleState(StrEnum):
    ACTIVE = "active"
    PICKED = "picked"
    EXPIRED = "expired"


class ReactionStateLifecycleOperation(StrEnum):
    EXPIRE = "expire"


class DendroCoreTerminationReason(StrEnum):
    EXPIRED = "expired"
    CAPACITY_EVICTED = "capacity_evicted"
    HYPERBLOOM_TRIGGERED = "hyperbloom_triggered"
    BURGEON_TRIGGERED = "burgeon_triggered"


class SprawlingShotResolution(StrEnum):
    ARRIVED = "arrived"
    LOST = "lost"


@dataclass(frozen=True, order=True, slots=True)
class ReactionStateScopeKey:
    """同一主体与 state slot 内的稳定实例作用域。"""

    value: str = "shared"

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("ReactionStateScopeKey 必须是非空字符串")


@dataclass(frozen=True, order=True, slots=True)
class ReactionStateInstanceRef:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("ReactionStateInstanceRef 必须是非空字符串")


@dataclass(frozen=True, slots=True)
class ScheduledStateTickCause:
    """周期 Effect 的稳定因果身份，禁止调用方任意命名。"""

    state_instance_ref: ReactionStateInstanceRef
    scheduled_frame: int
    tick_kind: ScheduledStateTickKind
    tick_index: int
    cause_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state_instance_ref, ReactionStateInstanceRef):
            raise ValueError("state_instance_ref 必须是 ReactionStateInstanceRef")
        _frame(self.scheduled_frame, "scheduled_frame")
        if not isinstance(self.tick_kind, ScheduledStateTickKind):
            raise ValueError("tick_kind 必须是 ScheduledStateTickKind")
        _frame(self.tick_index, "tick_index")
        if self.tick_index <= 0:
            raise ValueError("tick_index 必须为正整数")
        expected = (
            f"reaction-state-tick:{self.state_instance_ref.value}:"
            f"frame:{self.scheduled_frame}:kind:{self.tick_kind.value}:"
            f"index:{self.tick_index}"
        )
        if self.cause_ref is not None and self.cause_ref != expected:
            raise ValueError("cause_ref 必须由 state instance、frame、kind 和 index 确定性派生")
        object.__setattr__(self, "cause_ref", expected)


@dataclass(frozen=True, order=True, slots=True)
class ReactionStateSlotKey:
    subject_ref: ElementalSubjectRef
    slot: ReactionStateSlot
    scope_key: ReactionStateScopeKey = ReactionStateScopeKey()

    def __post_init__(self) -> None:
        if not isinstance(self.scope_key, ReactionStateScopeKey):
            raise TypeError("ReactionStateSlotKey.scope_key 必须是 ReactionStateScopeKey")


@dataclass(frozen=True, slots=True)
class FrozenState:
    """活动冻结的 Link、生命周期与速率历史，不复制冻元素量。"""

    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    state_link_ref: ElementalStateLinkRef
    created_frame: int
    next_required_frame: int | None = None
    decay_rate: float = MIN_FREEZE_DECAY_RATE
    decay_rate_updated_frame: int | None = None

    def __post_init__(self) -> None:
        _frame(self.created_frame, "created_frame")
        if self.next_required_frame is not None:
            _frame(self.next_required_frame, "next_required_frame")
            if self.next_required_frame < self.created_frame:
                raise ValueError("next_required_frame 不能早于 created_frame")
        if not isinstance(self.decay_rate, (int, float)) or not math.isfinite(self.decay_rate):
            raise ValueError("decay_rate 必须是有限数值")
        if self.decay_rate < MIN_FREEZE_DECAY_RATE:
            raise ValueError("decay_rate 不能低于冻结最小衰减速率")
        updated_frame = (
            self.created_frame
            if self.decay_rate_updated_frame is None
            else self.decay_rate_updated_frame
        )
        _frame(updated_frame, "decay_rate_updated_frame")
        if updated_frame < self.created_frame:
            raise ValueError("decay_rate_updated_frame 不能早于 created_frame")
        object.__setattr__(self, "decay_rate", float(self.decay_rate))
        object.__setattr__(self, "decay_rate_updated_frame", updated_frame)

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(self.subject_ref, ReactionStateSlot.FROZEN)


@dataclass(frozen=True, slots=True)
class FreezeRecoveryState:
    """解冻后的衰减速率恢复历史，不代表目标仍处于冻结。"""

    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    decay_rate: float
    decay_rate_updated_frame: int

    def __post_init__(self) -> None:
        if not isinstance(self.decay_rate, (int, float)) or not math.isfinite(self.decay_rate):
            raise ValueError("decay_rate 必须是有限数值")
        if self.decay_rate < MIN_FREEZE_DECAY_RATE:
            raise ValueError("decay_rate 不能低于冻结最小衰减速率")
        _frame(self.decay_rate_updated_frame, "decay_rate_updated_frame")
        object.__setattr__(self, "decay_rate", float(self.decay_rate))

    @property
    def next_required_frame(self) -> None:
        return None

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(self.subject_ref, ReactionStateSlot.FREEZE_RECOVERY)


@dataclass(frozen=True, slots=True)
class ElectroChargedState:
    """感电的来源快照与周期游标；水雷元素量只由 Aura 保存。"""

    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    created_by_occurrence_ref: str
    current_effect_owner: ElementalSourceRef
    captured_scaling_basis: CapturedTransformativeScalingBasis
    created_frame: int
    next_tick_frame: int
    next_tick_index: int
    revision: int = 1

    def __post_init__(self) -> None:
        from genshin_sim.core.systems.reaction.models import CapturedTransformativeScalingBasis

        if (
            not isinstance(self.created_by_occurrence_ref, str)
            or not self.created_by_occurrence_ref
        ):
            raise ValueError("created_by_occurrence_ref 必须是非空字符串")
        if not isinstance(self.current_effect_owner, ElementalSourceRef):
            raise ValueError("current_effect_owner 必须是 ElementalSourceRef")
        if not isinstance(self.captured_scaling_basis, CapturedTransformativeScalingBasis):
            raise ValueError("captured_scaling_basis 必须是 CapturedTransformativeScalingBasis")
        if self.captured_scaling_basis.source_ref != self.current_effect_owner:
            raise ValueError("感电来源与捕获缩放来源必须一致")
        _frame(self.created_frame, "created_frame")
        _frame(self.next_tick_frame, "next_tick_frame")
        if self.next_tick_frame <= self.created_frame:
            raise ValueError("next_tick_frame 必须晚于 created_frame")
        _frame(self.next_tick_index, "next_tick_index")
        if self.next_tick_index <= 0:
            raise ValueError("next_tick_index 必须为正整数")
        _frame(self.revision, "revision")
        if self.revision <= 0:
            raise ValueError("revision 必须为正整数")

    @property
    def next_required_frame(self) -> int:
        return self.next_tick_frame

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(self.subject_ref, ReactionStateSlot.ELECTRO_CHARGED)


@dataclass(frozen=True, slots=True)
class BurningState:
    """燃烧的共享 Link、来源快照与彼此独立的伤害/火附着周期游标。"""

    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    burning_aura_link_ref: ElementalStateLinkRef
    dendro_like_link_refs: tuple[ElementalStateLinkRef, ...]
    created_by_occurrence_ref: str
    current_effect_owner: ElementalSourceRef
    captured_scaling_basis: CapturedTransformativeScalingBasis
    created_frame: int
    next_dendro_like_depletion_frame: int
    next_damage_tick_frame: int
    next_damage_tick_index: int
    next_pyro_application_frame: int
    next_pyro_application_index: int
    revision: int = 1

    def __post_init__(self) -> None:
        from genshin_sim.core.systems.reaction.models import CapturedTransformativeScalingBasis

        if (
            not isinstance(self.created_by_occurrence_ref, str)
            or not self.created_by_occurrence_ref
        ):
            raise ValueError("created_by_occurrence_ref 必须是非空字符串")
        if not isinstance(self.burning_aura_link_ref, ElementalStateLinkRef):
            raise ValueError("burning_aura_link_ref 必须是 ElementalStateLinkRef")
        dendro_like_link_refs = tuple(self.dendro_like_link_refs)
        if not dendro_like_link_refs or not all(
            isinstance(item, ElementalStateLinkRef) for item in dendro_like_link_refs
        ):
            raise ValueError("dendro_like_link_refs 必须包含 ElementalStateLinkRef")
        if self.burning_aura_link_ref not in dendro_like_link_refs:
            raise ValueError("类草 Link 必须包含 Burning Link")
        if not isinstance(self.current_effect_owner, ElementalSourceRef):
            raise ValueError("current_effect_owner 必须是 ElementalSourceRef")
        if not isinstance(self.captured_scaling_basis, CapturedTransformativeScalingBasis):
            raise ValueError("captured_scaling_basis 必须是 CapturedTransformativeScalingBasis")
        if self.captured_scaling_basis.source_ref != self.current_effect_owner:
            raise ValueError("燃烧来源与捕获缩放来源必须一致")
        _frame(self.created_frame, "created_frame")
        for value, name in (
            (self.next_dendro_like_depletion_frame, "next_dendro_like_depletion_frame"),
            (self.next_damage_tick_frame, "next_damage_tick_frame"),
            (self.next_pyro_application_frame, "next_pyro_application_frame"),
        ):
            _frame(value, name)
            if value <= self.created_frame:
                raise ValueError(f"{name} 必须晚于 created_frame")
        for value, name in (
            (self.next_damage_tick_index, "next_damage_tick_index"),
            (self.next_pyro_application_index, "next_pyro_application_index"),
            (self.revision, "revision"),
        ):
            _frame(value, name)
            if value <= 0:
                raise ValueError(f"{name} 必须为正整数")
        object.__setattr__(self, "dendro_like_link_refs", dendro_like_link_refs)

    @property
    def next_required_frame(self) -> int:
        return min(
            self.next_dendro_like_depletion_frame,
            self.next_damage_tick_frame,
            self.next_pyro_application_frame,
        )

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(self.subject_ref, ReactionStateSlot.BURNING)


@dataclass(frozen=True, slots=True)
class QuickenState:
    """活动激化状态的身份、Link 与最近 occurrence；激元素量只由 Aura 保存。"""

    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    quicken_aura_link_ref: ElementalStateLinkRef
    created_by_occurrence_ref: str
    last_updated_by_occurrence_ref: str
    created_frame: int
    revision: int = 1

    def __post_init__(self) -> None:
        for value, name in (
            (self.created_by_occurrence_ref, "created_by_occurrence_ref"),
            (self.last_updated_by_occurrence_ref, "last_updated_by_occurrence_ref"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串")
        if not isinstance(self.quicken_aura_link_ref, ElementalStateLinkRef):
            raise ValueError("quicken_aura_link_ref 必须是 ElementalStateLinkRef")
        _frame(self.created_frame, "created_frame")
        _frame(self.revision, "revision")
        if self.revision <= 0:
            raise ValueError("revision 必须为正整数")

    @property
    def next_required_frame(self) -> None:
        return None

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(self.subject_ref, ReactionStateSlot.QUICKEN)


@dataclass(frozen=True, slots=True)
class CrystallizeShardState:
    """结晶晶片的语义、捕获基础与终态；空间投影由 Space 单独拥有。"""

    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    space_entity_ref: str
    element: Element
    created_by_occurrence_ref: str
    trigger_source: ElementalSourceRef
    captured_shield_basis: CapturedCrystallizeShieldBasis
    created_frame: int
    expires_at_frame: int
    lifecycle_state: CrystallizeShardLifecycleState = CrystallizeShardLifecycleState.ACTIVE
    terminal_frame: int | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        from genshin_sim.core.systems.reaction.models import CapturedCrystallizeShieldBasis

        for value, name in (
            (self.space_entity_ref, "space_entity_ref"),
            (self.created_by_occurrence_ref, "created_by_occurrence_ref"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串")
        expected_instance_ref = f"reaction-state:crystallize-shard:{self.created_by_occurrence_ref}"
        if self.instance_ref.value != expected_instance_ref:
            raise ValueError("结晶晶片 instance_ref 必须由 occurrence_ref 确定性派生")
        expected_space_entity_ref = (
            f"reaction_object:crystallize_shard:{self.created_by_occurrence_ref}"
        )
        if self.space_entity_ref != expected_space_entity_ref:
            raise ValueError("结晶晶片 space_entity_ref 必须由 occurrence_ref 确定性派生")
        if not isinstance(self.element, Element) or self.element not in {
            Element.PYRO,
            Element.HYDRO,
            Element.ELECTRO,
            Element.CRYO,
        }:
            raise ValueError("结晶晶片 element 必须是火、水、雷或冰")
        if not isinstance(self.trigger_source, ElementalSourceRef):
            raise ValueError("trigger_source 必须是 ElementalSourceRef")
        if not isinstance(self.captured_shield_basis, CapturedCrystallizeShieldBasis):
            raise ValueError("captured_shield_basis 必须是 CapturedCrystallizeShieldBasis")
        if self.captured_shield_basis.source_ref != self.trigger_source:
            raise ValueError("结晶晶片来源必须与捕获基础一致")
        _frame(self.created_frame, "created_frame")
        _frame(self.expires_at_frame, "expires_at_frame")
        if self.expires_at_frame <= self.created_frame:
            raise ValueError("expires_at_frame 必须晚于 created_frame")
        if self.captured_shield_basis.captured_frame != self.created_frame:
            raise ValueError("捕获基础的 captured_frame 必须与创建帧一致")
        if not isinstance(self.lifecycle_state, CrystallizeShardLifecycleState):
            raise ValueError("lifecycle_state 必须是 CrystallizeShardLifecycleState")
        if self.lifecycle_state is CrystallizeShardLifecycleState.ACTIVE:
            if self.terminal_frame is not None:
                raise ValueError("活动晶片不能有 terminal_frame")
        else:
            if self.terminal_frame is None:
                raise ValueError("终态晶片必须有 terminal_frame")
            _frame(self.terminal_frame, "terminal_frame")
            if self.lifecycle_state is CrystallizeShardLifecycleState.PICKED and not (
                self.created_frame <= self.terminal_frame < self.expires_at_frame
            ):
                raise ValueError("拾取帧必须处于晶片活动区间")
            if (
                self.lifecycle_state is CrystallizeShardLifecycleState.EXPIRED
                and self.terminal_frame != self.expires_at_frame
            ):
                raise ValueError("到期晶片的 terminal_frame 必须等于 expires_at_frame")
        _frame(self.revision, "revision")
        if self.revision <= 0:
            raise ValueError("revision 必须为正整数")

    @property
    def next_required_frame(self) -> int | None:
        return (
            self.expires_at_frame
            if self.lifecycle_state is CrystallizeShardLifecycleState.ACTIVE
            else None
        )

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(
            self.subject_ref,
            ReactionStateSlot.CRYSTALLIZE_SHARD,
            ReactionStateScopeKey(self.instance_ref.value),
        )


@dataclass(frozen=True, slots=True)
class DendroCoreState:
    """活动草原核的单一真值；终态仅存在于提交回执和领域事实中。"""

    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    space_entity_ref: str
    created_by_occurrence_ref: str
    core_creator_ref: ElementalSourceRef
    dynamic_scaling_basis: DynamicTransformativeScalingBasis
    pool_scope: str
    created_frame: int
    expires_at_frame: int
    creation_sequence: int
    revision: int = 1

    def __post_init__(self) -> None:
        from genshin_sim.core.systems.reaction.models import DynamicTransformativeScalingBasis

        for value, name in (
            (self.space_entity_ref, "space_entity_ref"),
            (self.created_by_occurrence_ref, "created_by_occurrence_ref"),
            (self.pool_scope, "pool_scope"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串")
        expected_instance_ref = f"reaction-state:dendro-core:{self.created_by_occurrence_ref}"
        if self.instance_ref.value != expected_instance_ref:
            raise ValueError("草原核 instance_ref 必须由 occurrence_ref 确定性派生")
        expected_space_entity_ref = f"reaction_object:dendro_core:{self.created_by_occurrence_ref}"
        if self.space_entity_ref != expected_space_entity_ref:
            raise ValueError("草原核 space_entity_ref 必须由 occurrence_ref 确定性派生")
        if not isinstance(self.core_creator_ref, ElementalSourceRef):
            raise ValueError("core_creator_ref 必须是 ElementalSourceRef")
        if not isinstance(self.dynamic_scaling_basis, DynamicTransformativeScalingBasis):
            raise ValueError("dynamic_scaling_basis 必须是 DynamicTransformativeScalingBasis")
        if self.dynamic_scaling_basis.source_ref != self.core_creator_ref:
            raise ValueError("草原核动态缩放来源必须与创建者一致")
        _frame(self.created_frame, "created_frame")
        _frame(self.expires_at_frame, "expires_at_frame")
        if self.expires_at_frame != self.created_frame + 360:
            raise ValueError("草原核生命周期必须固定为 360 帧")
        _frame(self.creation_sequence, "creation_sequence")
        if self.creation_sequence <= 0:
            raise ValueError("creation_sequence 必须为正整数")
        _frame(self.revision, "revision")
        if self.revision <= 0:
            raise ValueError("revision 必须为正整数")

    @property
    def next_required_frame(self) -> int:
        return self.expires_at_frame

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(
            self.subject_ref,
            ReactionStateSlot.DENDRO_CORE,
            ReactionStateScopeKey(self.instance_ref.value),
        )


@dataclass(frozen=True, slots=True)
class LunarStormCloudState:
    """雷暴云的生命周期、所属队伍与独立攻击游标；位置投影由 Space 保存。"""

    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    space_entity_ref: str
    created_by_occurrence_ref: str
    trigger_source_ref: ElementalSourceRef
    team_ref: str
    created_frame: int
    expires_at_frame: int
    next_attack_frame: int
    next_attack_index: int
    attack_interval_frames: int
    revision: int = 1

    def __post_init__(self) -> None:
        for value, name in (
            (self.space_entity_ref, "space_entity_ref"),
            (self.created_by_occurrence_ref, "created_by_occurrence_ref"),
            (self.team_ref, "team_ref"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串")
        expected_instance_ref = f"reaction-state:lunar-storm-cloud:{self.created_by_occurrence_ref}"
        if self.instance_ref.value != expected_instance_ref:
            raise ValueError("雷暴云 instance_ref 必须由 occurrence_ref 确定性派生")
        expected_space_entity_ref = (
            f"reaction_object:lunar_storm_cloud:{self.created_by_occurrence_ref}"
        )
        if self.space_entity_ref != expected_space_entity_ref:
            raise ValueError("雷暴云 space_entity_ref 必须由 occurrence_ref 确定性派生")
        if not isinstance(self.trigger_source_ref, ElementalSourceRef):
            raise ValueError("trigger_source_ref 必须是 ElementalSourceRef")
        _frame(self.created_frame, "created_frame")
        _frame(self.expires_at_frame, "expires_at_frame")
        if self.expires_at_frame < self.created_frame + 360:
            raise ValueError("雷暴云生命周期至少为 360 帧")
        _frame(self.next_attack_frame, "next_attack_frame")
        if self.next_attack_frame <= self.created_frame:
            raise ValueError("next_attack_frame 必须晚于 created_frame")
        _frame(self.next_attack_index, "next_attack_index")
        if self.next_attack_index <= 0:
            raise ValueError("next_attack_index 必须为正整数")
        if (
            isinstance(self.attack_interval_frames, bool)
            or not isinstance(self.attack_interval_frames, int)
            or self.attack_interval_frames != 15
        ):
            raise ValueError("雷暴云攻击间隔必须固定为 15 帧")
        _frame(self.revision, "revision")
        if self.revision <= 0:
            raise ValueError("revision 必须为正整数")

    @property
    def next_required_frame(self) -> int:
        return min(self.next_attack_frame, self.expires_at_frame)

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(
            self.subject_ref,
            ReactionStateSlot.LUNAR_STORM_CLOUD,
            ReactionStateScopeKey(self.instance_ref.value),
        )


@dataclass(frozen=True, slots=True)
class LunarCageState:
    """月笼的生命周期、发射冷却与最后一次谐奏帧；位置投影由 Space 保存。"""

    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    space_entity_ref: str
    created_by_occurrence_ref: str
    trigger_source_ref: ElementalSourceRef
    team_ref: str
    created_frame: int
    last_harmony_frame: int
    next_attack_frame: int
    expires_at_frame: int
    attack_index: int
    revision: int = 1

    def __post_init__(self) -> None:
        for value, name in (
            (self.space_entity_ref, "space_entity_ref"),
            (self.created_by_occurrence_ref, "created_by_occurrence_ref"),
            (self.team_ref, "team_ref"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串")
        instance_prefix = f"reaction-state:lunar-cage:{self.created_by_occurrence_ref}:"
        space_prefix = f"reaction_object:lunar_cage:{self.created_by_occurrence_ref}:"
        if not self.instance_ref.value.startswith(instance_prefix):
            raise ValueError("月笼 instance_ref 必须由 occurrence_ref 和序号确定性派生")
        if self.instance_ref.value.removeprefix(instance_prefix) not in {"0", "1", "2"}:
            raise ValueError("月笼 instance_ref 序号必须位于 0~2")
        if not self.space_entity_ref.startswith(space_prefix):
            raise ValueError("月笼 space_entity_ref 必须由 occurrence_ref 和序号确定性派生")
        if self.space_entity_ref.removeprefix(space_prefix) not in {"0", "1", "2"}:
            raise ValueError("月笼 space_entity_ref 序号必须位于 0~2")
        if not isinstance(self.trigger_source_ref, ElementalSourceRef):
            raise ValueError("trigger_source_ref 必须是 ElementalSourceRef")
        _frame(self.created_frame, "created_frame")
        _frame(self.last_harmony_frame, "last_harmony_frame")
        _frame(self.next_attack_frame, "next_attack_frame")
        _frame(self.expires_at_frame, "expires_at_frame")
        if self.last_harmony_frame < self.created_frame:
            raise ValueError("last_harmony_frame 不能早于 created_frame")
        if self.next_attack_frame < self.created_frame:
            raise ValueError("next_attack_frame 不能早于 created_frame")
        if self.expires_at_frame != self.last_harmony_frame + 540:
            raise ValueError("月笼生命周期必须固定为最后一次谐奏后 540 帧")
        _frame(self.attack_index, "attack_index")
        _frame(self.revision, "revision")
        if self.revision <= 0:
            raise ValueError("revision 必须为正整数")

    @property
    def next_required_frame(self) -> int:
        return self.expires_at_frame

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(
            self.subject_ref,
            ReactionStateSlot.LUNAR_CAGE,
            ReactionStateScopeKey(self.instance_ref.value),
        )


@dataclass(frozen=True, order=True, slots=True)
class LunarCrystallizeOccurrenceRecord:
    """单次月结晶的参与者历史；供谐奏按 occurrence 顺序消费。"""

    occurrence_ref: str
    frame: int
    order: int
    participant_refs: tuple[ElementalSourceRef, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.occurrence_ref, str) or not self.occurrence_ref.strip():
            raise ValueError("occurrence_ref 必须是非空字符串")
        _frame(self.frame, "frame")
        _frame(self.order, "order")
        participant_refs = tuple(self.participant_refs)
        if any(not isinstance(item, ElementalSourceRef) for item in participant_refs):
            raise ValueError("participant_refs 必须是 ElementalSourceRef 序列")
        if len(set(participant_refs)) != len(participant_refs):
            raise ValueError("participant_refs 不能重复")
        object.__setattr__(self, "participant_refs", tuple(sorted(participant_refs)))


@dataclass(frozen=True, slots=True)
class LunarCrystallizeAccumulatorState:
    """队伍级月结晶共享累计；按 occurrence 顺序保存至多 4 层记录。"""

    instance_ref: ReactionStateInstanceRef
    team_ref: str
    subject_ref: ElementalSubjectRef
    pending_records: tuple[LunarCrystallizeOccurrenceRecord, ...]
    max_layers: int = 4
    revision: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        if not isinstance(self.team_ref, str) or not self.team_ref.strip():
            raise ValueError("team_ref 必须是非空字符串")
        expected_instance_ref = f"reaction-state:lunar-crystallize-accumulator:{self.team_ref}"
        if self.instance_ref.value != expected_instance_ref:
            raise ValueError("累计器 instance_ref 必须由 team_ref 确定性派生")
        if not isinstance(self.subject_ref, ElementalSubjectRef):
            raise ValueError("subject_ref 必须是 ElementalSubjectRef")
        records = tuple(self.pending_records)
        if any(not isinstance(item, LunarCrystallizeOccurrenceRecord) for item in records):
            raise ValueError("pending_records 必须是 LunarCrystallizeOccurrenceRecord 序列")
        if len({item.occurrence_ref for item in records}) != len(records):
            raise ValueError("pending_records 不能包含重复 occurrence")
        ordered = tuple(
            sorted(records, key=lambda item: (item.frame, item.order, item.occurrence_ref))
        )
        if ordered != records:
            raise ValueError("pending_records 必须按 occurrence 顺序排列")
        if self.max_layers != 4:
            raise ValueError("月结晶累计器最多储存 4 层")
        if len(records) > self.max_layers:
            raise ValueError("pending_records 超过累计器容量")
        _frame(self.revision, "revision")
        if self.revision <= 0:
            raise ValueError("revision 必须为正整数")
        object.__setattr__(self, "pending_records", ordered)

    @property
    def next_required_frame(self) -> int | None:
        return None

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(
            self.subject_ref,
            ReactionStateSlot.LUNAR_CRYSTALLIZE_ACCUMULATOR,
            ReactionStateScopeKey(self.team_ref),
        )


@dataclass(frozen=True, slots=True)
class SprawlingShotState:
    """超绽放锁定目标后的蔓生弹状态，不声明未确认的飞行时间。"""

    instance_ref: ReactionStateInstanceRef
    space_entity_ref: str
    source_core_ref: ReactionStateInstanceRef
    trigger_occurrence_ref: str
    trigger_source_ref: ElementalSourceRef
    dynamic_scaling_basis: DynamicTransformativeScalingBasis
    selected_target_ref: ElementalSubjectRef
    created_frame: int
    revision: int = 1

    def __post_init__(self) -> None:
        from genshin_sim.core.systems.reaction.models import DynamicTransformativeScalingBasis

        if not self.space_entity_ref.strip():
            raise ValueError("space_entity_ref 必须是非空字符串")
        if not isinstance(self.source_core_ref, ReactionStateInstanceRef):
            raise ValueError("source_core_ref 必须是 ReactionStateInstanceRef")
        if not isinstance(self.trigger_occurrence_ref, str):
            raise ValueError("trigger_occurrence_ref 必须是非空字符串")
        if not self.trigger_occurrence_ref.strip():
            raise ValueError("trigger_occurrence_ref 必须是非空字符串")
        if not isinstance(self.trigger_source_ref, ElementalSourceRef):
            raise ValueError("trigger_source_ref 必须是 ElementalSourceRef")
        if not isinstance(self.dynamic_scaling_basis, DynamicTransformativeScalingBasis):
            raise ValueError("dynamic_scaling_basis 必须是 DynamicTransformativeScalingBasis")
        if self.dynamic_scaling_basis.source_ref != self.trigger_source_ref:
            raise ValueError("蔓生弹动态缩放来源必须与触发来源一致")
        expected_space_entity_ref = f"reaction_object:sprawling_shot:{self.instance_ref.value}"
        if self.space_entity_ref != expected_space_entity_ref:
            raise ValueError("蔓生弹 space_entity_ref 必须由 instance_ref 确定性派生")
        _frame(self.created_frame, "created_frame")
        _frame(self.revision, "revision")
        if self.revision <= 0:
            raise ValueError("revision 必须为正整数")

    @property
    def next_required_frame(self) -> None:
        return None

    @property
    def subject_ref(self) -> ElementalSubjectRef:
        """State Store 的通用主体投影，语义上等于已锁定目标。"""

        return self.selected_target_ref

    @property
    def created_by_occurrence_ref(self) -> str:
        """从稳定的来源核心身份恢复原始绽放 occurrence。"""

        prefix = "reaction-state:dendro-core:"
        if not self.source_core_ref.value.startswith(prefix):
            raise ValueError("蔓生弹 source_core_ref 必须引用草原核 State")
        return self.source_core_ref.value.removeprefix(prefix)

    @property
    def slot_key(self) -> ReactionStateSlotKey:
        return ReactionStateSlotKey(
            self.selected_target_ref,
            ReactionStateSlot.SPRAWLING_SHOT,
            ReactionStateScopeKey(self.instance_ref.value),
        )


type ReactionStateRecord = (
    BurningState
    | CrystallizeShardState
    | DendroCoreState
    | ElectroChargedState
    | FreezeRecoveryState
    | FrozenState
    | LunarCageState
    | LunarCrystallizeAccumulatorState
    | LunarStormCloudState
    | QuickenState
    | SprawlingShotState
)
_REACTION_STATE_RECORD_TYPES = (
    BurningState,
    CrystallizeShardState,
    DendroCoreState,
    ElectroChargedState,
    FreezeRecoveryState,
    FrozenState,
    LunarCageState,
    LunarCrystallizeAccumulatorState,
    LunarStormCloudState,
    QuickenState,
    SprawlingShotState,
)


@dataclass(frozen=True, slots=True)
class ReactionStateChange:
    slot_key: ReactionStateSlotKey
    before: ReactionStateRecord | None
    after: ReactionStateRecord | None


@dataclass(frozen=True, slots=True)
class ReactionStateMutationPlan:
    operation_id: str
    frame: int
    expected_store_version: int
    expected_records: tuple[ReactionStateRecord, ...]
    replacement_records: tuple[ReactionStateRecord, ...]
    removed_slot_keys: tuple[ReactionStateSlotKey, ...]
    changes: tuple[ReactionStateChange, ...]
    next_state_instance_sequence: int
    next_dendro_core_creation_sequence: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ValueError("operation_id 必须是非空字符串")
        _frame(self.frame, "frame")
        _frame(self.expected_store_version, "expected_store_version")
        _frame(self.next_state_instance_sequence, "next_state_instance_sequence")
        _frame(self.next_dendro_core_creation_sequence, "next_dendro_core_creation_sequence")
        replacements = tuple(self.replacement_records)
        removed = tuple(self.removed_slot_keys)
        if any(not isinstance(record, _REACTION_STATE_RECORD_TYPES) for record in replacements):
            raise ValueError("ReactionState replacement_records 包含不受支持的状态记录")
        if any(
            not isinstance(record, _REACTION_STATE_RECORD_TYPES) for record in self.expected_records
        ):
            raise ValueError("ReactionState expected_records 包含不受支持的状态记录")
        if len({item.slot_key for item in replacements}) != len(replacements):
            raise ValueError("ReactionState replacement slot 不能重复")
        if len(set(removed)) != len(removed):
            raise ValueError("ReactionState removed slot 不能重复")
        if {item.slot_key for item in replacements} & set(removed):
            raise ValueError("ReactionState replacement 与 remove 不能重叠")
        object.__setattr__(self, "expected_records", tuple(self.expected_records))
        object.__setattr__(self, "replacement_records", replacements)
        object.__setattr__(self, "removed_slot_keys", removed)
        object.__setattr__(self, "changes", tuple(self.changes))


@dataclass(frozen=True, slots=True)
class ReactionStateCommitReceipt:
    plan: ReactionStateMutationPlan
    version: int


@dataclass(frozen=True, slots=True)
class ReactionStateSnapshot:
    frame: int
    normalized_through_frame: int
    version: int
    records: tuple[ReactionStateRecord, ...]


@dataclass(frozen=True, slots=True)
class ElectroChargedTickRootWork:
    """普通感电单周期根工作。后续状态类型以独立类型加入联合。"""

    work_id: str
    frame: int
    root_order: int
    state_instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    tick_index: int
    cause: ScheduledStateTickCause | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.work_id, str) or not self.work_id.strip():
            raise ValueError("work_id 必须是非空字符串")
        _frame(self.frame, "frame")
        _frame(self.root_order, "root_order")
        _frame(self.tick_index, "tick_index")
        if self.tick_index <= 0:
            raise ValueError("tick_index 必须为正整数")
        expected_work_id = (
            f"reaction-state:{self.state_instance_ref.value}:"
            f"frame:{self.frame}:tick:{self.tick_index}"
        )
        if self.work_id != expected_work_id:
            raise ValueError(
                "感电 root 的 work_id 必须由 state instance、frame 和 tick index 确定性派生"
            )
        cause = self.cause or ScheduledStateTickCause(
            state_instance_ref=self.state_instance_ref,
            scheduled_frame=self.frame,
            tick_kind=ScheduledStateTickKind.ELECTRO_CHARGED_PULSE,
            tick_index=self.tick_index,
        )
        if not isinstance(cause, ScheduledStateTickCause):
            raise ValueError("cause 必须是 ScheduledStateTickCause")
        if (
            cause.state_instance_ref != self.state_instance_ref
            or cause.scheduled_frame != self.frame
            or cause.tick_kind is not ScheduledStateTickKind.ELECTRO_CHARGED_PULSE
            or cause.tick_index != self.tick_index
        ):
            raise ValueError("感电 root 的 cause 必须与 root identity 一致")
        object.__setattr__(self, "cause", cause)

    @property
    def state_slot(self) -> ReactionStateSlot:
        return ReactionStateSlot.ELECTRO_CHARGED

    @property
    def cause_ref(self) -> str:
        assert self.cause is not None
        cause_ref = self.cause.cause_ref
        if cause_ref is None:
            raise RuntimeError("已验证的 scheduled cause 缺少 cause_ref")
        return cause_ref


@dataclass(frozen=True, slots=True)
class BurningCycleRootWork:
    """燃烧同帧伤害和火附着的组合 root；两个 cause 保持独立。"""

    work_id: str
    frame: int
    root_order: int
    state_instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    damage_tick_index: int | None = None
    pyro_application_index: int | None = None
    damage_cause: ScheduledStateTickCause | None = None
    pyro_cause: ScheduledStateTickCause | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.work_id, str) or not self.work_id.strip():
            raise ValueError("work_id 必须是非空字符串")
        _frame(self.frame, "frame")
        _frame(self.root_order, "root_order")
        if self.damage_tick_index is None and self.pyro_application_index is None:
            raise ValueError("燃烧 cycle root 至少需要一个 due cursor")
        for value, name in (
            (self.damage_tick_index, "damage_tick_index"),
            (self.pyro_application_index, "pyro_application_index"),
        ):
            if value is not None:
                _frame(value, name)
                if value <= 0:
                    raise ValueError(f"{name} 必须为正整数")
        expected_work_id = (
            f"reaction-state:{self.state_instance_ref.value}:frame:{self.frame}:"
            f"burning:damage:{self.damage_tick_index or 0}:"
            f"pyro_application:{self.pyro_application_index or 0}"
        )
        if self.work_id != expected_work_id:
            raise ValueError(
                "燃烧 root 的 work_id 必须由 state instance、frame 和 due cursor 确定性派生"
            )
        damage_cause = self._validated_cause(
            self.damage_cause,
            tick_kind=ScheduledStateTickKind.BURNING_DAMAGE,
            tick_index=self.damage_tick_index,
            name="damage_cause",
        )
        pyro_cause = self._validated_cause(
            self.pyro_cause,
            tick_kind=ScheduledStateTickKind.BURNING_PYRO_APPLICATION,
            tick_index=self.pyro_application_index,
            name="pyro_cause",
        )
        object.__setattr__(self, "damage_cause", damage_cause)
        object.__setattr__(self, "pyro_cause", pyro_cause)

    def _validated_cause(
        self,
        cause: ScheduledStateTickCause | None,
        *,
        tick_kind: ScheduledStateTickKind,
        tick_index: int | None,
        name: str,
    ) -> ScheduledStateTickCause | None:
        if tick_index is None:
            if cause is not None:
                raise ValueError(f"{name} 不能对应未 due 的 cursor")
            return None
        resolved = cause or ScheduledStateTickCause(
            state_instance_ref=self.state_instance_ref,
            scheduled_frame=self.frame,
            tick_kind=tick_kind,
            tick_index=tick_index,
        )
        if not isinstance(resolved, ScheduledStateTickCause):
            raise ValueError(f"{name} 必须是 ScheduledStateTickCause")
        if (
            resolved.state_instance_ref != self.state_instance_ref
            or resolved.scheduled_frame != self.frame
            or resolved.tick_kind is not tick_kind
            or resolved.tick_index != tick_index
        ):
            raise ValueError(f"{name} 必须与 root identity 一致")
        return resolved

    @property
    def state_slot(self) -> ReactionStateSlot:
        return ReactionStateSlot.BURNING

    @property
    def causes(self) -> tuple[ScheduledStateTickCause, ...]:
        return tuple(cause for cause in (self.damage_cause, self.pyro_cause) if cause is not None)

    @property
    def scheduled_tick_index(self) -> int | None:
        """单 cause root 的旧审计字段投影；双 cause root 使用 causes 审计。"""

        if self.damage_tick_index is None:
            return self.pyro_application_index
        if self.pyro_application_index is None:
            return self.damage_tick_index
        return None


@dataclass(frozen=True, slots=True)
class LunarStormCloudAttackRootWork:
    """雷暴云单次周期攻击根工作。"""

    work_id: str
    frame: int
    root_order: int
    state_instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    cloud_position: Vector3
    tick_index: int
    cause: ScheduledStateTickCause | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.work_id, str) or not self.work_id.strip():
            raise ValueError("work_id 必须是非空字符串")
        _frame(self.frame, "frame")
        _frame(self.root_order, "root_order")
        if not isinstance(self.cloud_position, Vector3):
            raise ValueError("cloud_position 必须是 Vector3")
        _frame(self.tick_index, "tick_index")
        if self.tick_index <= 0:
            raise ValueError("tick_index 必须为正整数")
        expected_work_id = (
            f"reaction-state:{self.state_instance_ref.value}:"
            f"frame:{self.frame}:"
            f"lunar_storm_cloud_attack:{self.tick_index}"
        )
        if self.work_id != expected_work_id:
            raise ValueError(
                "雷暴云 root 的 work_id 必须由 state instance、frame 和 tick index 确定性派生"
            )
        cause = self.cause or ScheduledStateTickCause(
            state_instance_ref=self.state_instance_ref,
            scheduled_frame=self.frame,
            tick_kind=ScheduledStateTickKind.LUNAR_STORM_CLOUD_ATTACK,
            tick_index=self.tick_index,
        )
        if not isinstance(cause, ScheduledStateTickCause):
            raise ValueError("cause 必须是 ScheduledStateTickCause")
        if (
            cause.state_instance_ref != self.state_instance_ref
            or cause.scheduled_frame != self.frame
            or cause.tick_kind is not ScheduledStateTickKind.LUNAR_STORM_CLOUD_ATTACK
            or cause.tick_index != self.tick_index
        ):
            raise ValueError("雷暴云 root 的 cause 必须与 root identity 一致")
        object.__setattr__(self, "cause", cause)

    @property
    def state_slot(self) -> ReactionStateSlot:
        return ReactionStateSlot.LUNAR_STORM_CLOUD

    @property
    def cause_ref(self) -> str:
        assert self.cause is not None
        cause_ref = self.cause.cause_ref
        if cause_ref is None:
            raise RuntimeError("已验证的 scheduled cause 缺少 cause_ref")
        return cause_ref


type ScheduledReactionRootWork = (
    ElectroChargedTickRootWork | BurningCycleRootWork | LunarStormCloudAttackRootWork
)


@dataclass(frozen=True, slots=True)
class ReactionStateLifecycleWork:
    """在必需帧物化的非结算根状态生命周期工作。"""

    work_ref: str
    frame: int
    state_instance_ref: ReactionStateInstanceRef
    state_slot: ReactionStateSlot
    scope_key: ReactionStateScopeKey
    operation: ReactionStateLifecycleOperation
    cause_ref: str

    def __post_init__(self) -> None:
        for value, name in ((self.work_ref, "work_ref"), (self.cause_ref, "cause_ref")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串")
        _frame(self.frame, "frame")
        if self.state_slot not in {
            ReactionStateSlot.CRYSTALLIZE_SHARD,
            ReactionStateSlot.DENDRO_CORE,
            ReactionStateSlot.LUNAR_STORM_CLOUD,
            ReactionStateSlot.LUNAR_CAGE,
        }:
            raise ValueError("lifecycle work 只支持绑定空间实体的 Reaction State")
        if self.operation is not ReactionStateLifecycleOperation.EXPIRE:
            raise ValueError("lifecycle work 当前只支持 expire")
        if self.scope_key != ReactionStateScopeKey(self.state_instance_ref.value):
            raise ValueError("lifecycle work scope_key 必须由 state_instance_ref 确定性派生")


class _ReactionStateRuntime(Protocol):
    _state_records: dict[ReactionStateSlotKey, ReactionStateRecord]
    _state_instance_sequence: int
    _dendro_core_creation_sequence: int

    @property
    def version(self) -> int: ...


class ReactionStatePlanner:
    """ReactionState 的完整替换计划；查询和计划构造都不会修改 Store。"""

    def __init__(self, runtime: _ReactionStateRuntime, frame: int, batch_id: str) -> None:
        self._runtime = runtime
        self.frame = frame
        self.batch_id = batch_id
        self._original = dict(runtime._state_records)
        self._working = dict(runtime._state_records)
        self._expected_store_version = runtime.version
        self._instance_sequence = runtime._state_instance_sequence
        self._dendro_core_creation_sequence = runtime._dendro_core_creation_sequence
        self._sealed = False

    def frozen_for(self, subject_ref: ElementalSubjectRef) -> FrozenState | None:
        record = self._working.get(ReactionStateSlotKey(subject_ref, ReactionStateSlot.FROZEN))
        return record if isinstance(record, FrozenState) else None

    def freeze_recovery_for(
        self,
        subject_ref: ElementalSubjectRef,
    ) -> FreezeRecoveryState | None:
        record = self._working.get(
            ReactionStateSlotKey(subject_ref, ReactionStateSlot.FREEZE_RECOVERY)
        )
        return record if isinstance(record, FreezeRecoveryState) else None

    def electro_charged_for(
        self,
        subject_ref: ElementalSubjectRef,
    ) -> ElectroChargedState | None:
        record = self._working.get(
            ReactionStateSlotKey(subject_ref, ReactionStateSlot.ELECTRO_CHARGED)
        )
        return record if isinstance(record, ElectroChargedState) else None

    def burning_for(self, subject_ref: ElementalSubjectRef) -> BurningState | None:
        record = self._working.get(ReactionStateSlotKey(subject_ref, ReactionStateSlot.BURNING))
        return record if isinstance(record, BurningState) else None

    def quicken_for(self, subject_ref: ElementalSubjectRef) -> QuickenState | None:
        record = self._working.get(ReactionStateSlotKey(subject_ref, ReactionStateSlot.QUICKEN))
        return record if isinstance(record, QuickenState) else None

    def crystallize_shard_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> CrystallizeShardState | None:
        if not isinstance(instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        record = next(
            (
                item
                for item in self._working.values()
                if isinstance(item, CrystallizeShardState) and item.instance_ref == instance_ref
            ),
            None,
        )
        return record

    def dendro_core_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> DendroCoreState | None:
        if not isinstance(instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        return next(
            (
                item
                for item in self._working.values()
                if isinstance(item, DendroCoreState) and item.instance_ref == instance_ref
            ),
            None,
        )

    def active_dendro_cores(self, *, pool_scope: str | None = None) -> tuple[DendroCoreState, ...]:
        if pool_scope is not None and (not isinstance(pool_scope, str) or not pool_scope.strip()):
            raise ValueError("pool_scope 必须是非空字符串或 None")
        return tuple(
            sorted(
                (
                    item
                    for item in self._working.values()
                    if isinstance(item, DendroCoreState)
                    and (pool_scope is None or item.pool_scope == pool_scope)
                ),
                key=lambda item: (item.creation_sequence, item.instance_ref.value),
            )
        )

    def lunar_storm_cloud_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarStormCloudState | None:
        if not isinstance(instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        return next(
            (
                item
                for item in self._working.values()
                if isinstance(item, LunarStormCloudState) and item.instance_ref == instance_ref
            ),
            None,
        )

    def lunar_storm_cloud_for_space_entity(
        self,
        space_entity_ref: str,
    ) -> LunarStormCloudState | None:
        if not isinstance(space_entity_ref, str) or not space_entity_ref.strip():
            raise ValueError("space_entity_ref 必须是非空字符串")
        return next(
            (
                item
                for item in self._working.values()
                if isinstance(item, LunarStormCloudState)
                and item.space_entity_ref == space_entity_ref
            ),
            None,
        )

    def active_lunar_storm_clouds(
        self,
        *,
        team_ref: str | None = None,
    ) -> tuple[LunarStormCloudState, ...]:
        if team_ref is not None and (not isinstance(team_ref, str) or not team_ref.strip()):
            raise ValueError("team_ref 必须是非空字符串或 None")
        return tuple(
            sorted(
                (
                    item
                    for item in self._working.values()
                    if isinstance(item, LunarStormCloudState)
                    and (team_ref is None or item.team_ref == team_ref)
                ),
                key=lambda item: (item.created_frame, item.instance_ref.value),
            )
        )

    def lunar_cage_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarCageState | None:
        if not isinstance(instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        return next(
            (
                item
                for item in self._working.values()
                if isinstance(item, LunarCageState) and item.instance_ref == instance_ref
            ),
            None,
        )

    def lunar_cage_for_space_entity(
        self,
        space_entity_ref: str,
    ) -> LunarCageState | None:
        if not isinstance(space_entity_ref, str) or not space_entity_ref.strip():
            raise ValueError("space_entity_ref 必须是非空字符串")
        return next(
            (
                item
                for item in self._working.values()
                if isinstance(item, LunarCageState) and item.space_entity_ref == space_entity_ref
            ),
            None,
        )

    def active_lunar_cages(
        self,
        *,
        team_ref: str | None = None,
    ) -> tuple[LunarCageState, ...]:
        if team_ref is not None and (not isinstance(team_ref, str) or not team_ref.strip()):
            raise ValueError("team_ref 必须是非空字符串或 None")
        return tuple(
            sorted(
                (
                    item
                    for item in self._working.values()
                    if isinstance(item, LunarCageState)
                    and (team_ref is None or item.team_ref == team_ref)
                ),
                key=lambda item: (item.created_frame, item.instance_ref.value),
            )
        )

    def lunar_crystallize_accumulator_for(
        self,
        team_ref: str,
    ) -> LunarCrystallizeAccumulatorState | None:
        if not isinstance(team_ref, str) or not team_ref.strip():
            raise ValueError("team_ref 必须是非空字符串")
        return next(
            (
                item
                for item in self._working.values()
                if isinstance(item, LunarCrystallizeAccumulatorState) and item.team_ref == team_ref
            ),
            None,
        )

    def sprawling_shot_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> SprawlingShotState | None:
        if not isinstance(instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        return next(
            (
                item
                for item in self._working.values()
                if isinstance(item, SprawlingShotState) and item.instance_ref == instance_ref
            ),
            None,
        )

    def create_frozen(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        state_link_ref: ElementalStateLinkRef,
        next_required_frame: int | None = None,
        decay_rate: float = MIN_FREEZE_DECAY_RATE,
        decay_rate_updated_frame: int | None = None,
    ) -> FrozenState:
        self._assert_open()
        key = ReactionStateSlotKey(subject_ref, ReactionStateSlot.FROZEN)
        if key in self._working:
            raise ValueError("活动 FrozenState 必须使用完整替换，而不是重复创建")
        self._working.pop(
            ReactionStateSlotKey(subject_ref, ReactionStateSlot.FREEZE_RECOVERY),
            None,
        )
        if next_required_frame is not None and next_required_frame < self.frame:
            raise ValueError("next_required_frame 不能早于状态创建帧")
        state = FrozenState(
            ReactionStateInstanceRef(self._next_instance_ref()),
            subject_ref,
            state_link_ref,
            self.frame,
            next_required_frame,
            decay_rate,
            decay_rate_updated_frame,
        )
        self._working[key] = state
        return state

    def create_freeze_recovery(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        decay_rate: float,
        decay_rate_updated_frame: int | None = None,
    ) -> FreezeRecoveryState:
        self._assert_open()
        key = ReactionStateSlotKey(subject_ref, ReactionStateSlot.FREEZE_RECOVERY)
        if key in self._working:
            raise ValueError("FreezeRecoveryState 必须使用完整替换，而不是重复创建")
        if ReactionStateSlotKey(subject_ref, ReactionStateSlot.FROZEN) in self._working:
            raise ValueError("创建 FreezeRecoveryState 前必须移除活动 FrozenState")
        state = FreezeRecoveryState(
            ReactionStateInstanceRef(self._next_instance_ref()),
            subject_ref,
            decay_rate,
            self.frame if decay_rate_updated_frame is None else decay_rate_updated_frame,
        )
        self._working[key] = state
        return state

    def create_electro_charged(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        created_by_occurrence_ref: str,
        current_effect_owner: ElementalSourceRef,
        captured_scaling_basis: CapturedTransformativeScalingBasis,
        next_tick_frame: int,
        next_tick_index: int = 1,
    ) -> ElectroChargedState:
        self._assert_open()
        key = ReactionStateSlotKey(subject_ref, ReactionStateSlot.ELECTRO_CHARGED)
        if key in self._working:
            raise ValueError("活动 ElectroChargedState 必须使用完整替换，而不是重复创建")
        state = ElectroChargedState(
            ReactionStateInstanceRef(self._next_instance_ref()),
            subject_ref,
            created_by_occurrence_ref,
            current_effect_owner,
            captured_scaling_basis,
            self.frame,
            next_tick_frame,
            next_tick_index,
        )
        self._working[key] = state
        return state

    def create_burning(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        burning_aura_link_ref: ElementalStateLinkRef,
        dendro_like_link_refs: tuple[ElementalStateLinkRef, ...],
        created_by_occurrence_ref: str,
        current_effect_owner: ElementalSourceRef,
        captured_scaling_basis: CapturedTransformativeScalingBasis,
        next_dendro_like_depletion_frame: int,
        next_damage_tick_frame: int,
        next_damage_tick_index: int,
        next_pyro_application_frame: int,
        next_pyro_application_index: int,
    ) -> BurningState:
        self._assert_open()
        key = ReactionStateSlotKey(subject_ref, ReactionStateSlot.BURNING)
        if key in self._working:
            raise ValueError("活动 BurningState 必须使用完整替换，而不是重复创建")
        state = BurningState(
            ReactionStateInstanceRef(self._next_instance_ref()),
            subject_ref,
            burning_aura_link_ref,
            dendro_like_link_refs,
            created_by_occurrence_ref,
            current_effect_owner,
            captured_scaling_basis,
            self.frame,
            next_dendro_like_depletion_frame,
            next_damage_tick_frame,
            next_damage_tick_index,
            next_pyro_application_frame,
            next_pyro_application_index,
        )
        self._working[key] = state
        return state

    def create_quicken(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        quicken_aura_link_ref: ElementalStateLinkRef,
        created_by_occurrence_ref: str,
        last_updated_by_occurrence_ref: str | None = None,
    ) -> QuickenState:
        self._assert_open()
        key = ReactionStateSlotKey(subject_ref, ReactionStateSlot.QUICKEN)
        if key in self._working:
            raise ValueError("活动 QuickenState 必须使用完整替换，而不是重复创建")
        occurrence_ref = created_by_occurrence_ref
        state = QuickenState(
            ReactionStateInstanceRef(self._next_instance_ref()),
            subject_ref,
            quicken_aura_link_ref,
            occurrence_ref,
            occurrence_ref
            if last_updated_by_occurrence_ref is None
            else last_updated_by_occurrence_ref,
            self.frame,
        )
        self._working[key] = state
        return state

    def create_crystallize_shard(
        self,
        intent: CrystallizeShardStateCreationIntent,
    ) -> CrystallizeShardState:
        """吸收机制已声明的确定性晶片创建意图，不分配通用 State 序号。"""

        from genshin_sim.core.systems.reaction.models import CrystallizeShardStateCreationIntent

        self._assert_open()
        if not isinstance(intent, CrystallizeShardStateCreationIntent):
            raise ValueError("intent 必须是 CrystallizeShardStateCreationIntent")
        if intent.created_frame != self.frame:
            raise ValueError("结晶晶片创建意图帧必须与 State 批次一致")
        if self.crystallize_shard_for(intent.instance_ref) is not None:
            raise ValueError("结晶晶片 instance_ref 已存在")
        state = CrystallizeShardState(
            intent.instance_ref,
            intent.subject_ref,
            intent.space_entity_ref,
            intent.element,
            intent.parent_occurrence_ref,
            intent.trigger_source,
            intent.captured_shield_basis,
            intent.created_frame,
            intent.expires_at_frame,
        )
        if state.slot_key in self._working:
            raise ValueError("结晶晶片 State slot 已存在")
        self._working[state.slot_key] = state
        return state

    def create_dendro_core(
        self,
        intent: DendroCoreStateCreationIntent,
    ) -> DendroCoreState:
        """接受普通绽放声明的确定性核心创建意图。"""

        from genshin_sim.core.systems.reaction.models import DendroCoreStateCreationIntent

        self._assert_open()
        if not isinstance(intent, DendroCoreStateCreationIntent):
            raise ValueError("intent 必须是 DendroCoreStateCreationIntent")
        if intent.created_frame != self.frame:
            raise ValueError("草原核创建意图帧必须与 State 批次一致")
        if self.dendro_core_for(intent.instance_ref) is not None:
            raise ValueError("草原核 instance_ref 已存在")
        creation_sequence = intent.creation_sequence
        if creation_sequence == 0:
            self._dendro_core_creation_sequence += 1
            creation_sequence = self._dendro_core_creation_sequence
        elif creation_sequence <= self._dendro_core_creation_sequence:
            raise ValueError("草原核 creation_sequence 必须单调递增")
        else:
            self._dendro_core_creation_sequence = creation_sequence
        state = DendroCoreState(
            instance_ref=intent.instance_ref,
            subject_ref=intent.subject_ref,
            space_entity_ref=intent.space_entity_ref,
            created_by_occurrence_ref=intent.parent_occurrence_ref,
            core_creator_ref=intent.core_creator_ref,
            dynamic_scaling_basis=intent.dynamic_scaling_basis,
            pool_scope=intent.pool_scope,
            created_frame=intent.created_frame,
            expires_at_frame=intent.expires_at_frame,
            creation_sequence=creation_sequence,
        )
        if state.slot_key in self._working:
            raise ValueError("草原核 State slot 已存在")
        if any(
            item.creation_sequence == state.creation_sequence
            for item in self.active_dendro_cores(pool_scope=state.pool_scope)
        ):
            raise ValueError("同一草原核池的 creation_sequence 不能重复")
        self._working[state.slot_key] = state
        return state

    def remove_dendro_core(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
    ) -> DendroCoreState:
        self._assert_open()
        before = self.dendro_core_for(instance_ref)
        if before is None:
            raise ValueError("不存在可终结的 DendroCoreState")
        del self._working[before.slot_key]
        return before

    def create_lunar_storm_cloud(
        self,
        intent: LunarStormCloudStatePlanningIntent,
    ) -> LunarStormCloudState:
        """接受月感电声明的确定性雷暴云创建意图。"""

        from genshin_sim.core.systems.reaction.models import (
            LunarStormCloudStatePlanningIntent,
        )

        self._assert_open()
        if not isinstance(intent, LunarStormCloudStatePlanningIntent):
            raise ValueError("intent 必须是 LunarStormCloudStatePlanningIntent")
        if intent.created_frame != self.frame:
            raise ValueError("雷暴云创建意图帧必须与 State 批次一致")
        if self.lunar_storm_cloud_for(intent.instance_ref) is not None:
            raise ValueError("雷暴云 instance_ref 已存在")
        state = LunarStormCloudState(
            instance_ref=intent.instance_ref,
            subject_ref=intent.subject_ref,
            space_entity_ref=intent.space_entity_ref,
            created_by_occurrence_ref=intent.parent_occurrence_ref,
            trigger_source_ref=intent.trigger_source_ref,
            team_ref=intent.team_ref,
            created_frame=intent.created_frame,
            expires_at_frame=intent.expires_at_frame,
            next_attack_frame=intent.first_attack_frame,
            next_attack_index=1,
            attack_interval_frames=intent.attack_interval_frames,
        )
        if state.slot_key in self._working:
            raise ValueError("雷暴云 State slot 已存在")
        self._working[state.slot_key] = state
        return state

    def replace_lunar_storm_cloud(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
        expires_at_frame: int,
    ) -> LunarStormCloudState:
        """刷新雷暴云存在时间；保留实例身份、触发来源与攻击游标。"""

        self._assert_open()
        before = self.lunar_storm_cloud_for(instance_ref)
        if before is None:
            raise ValueError("不存在可刷新的 LunarStormCloudState")
        _frame(expires_at_frame, "expires_at_frame")
        if expires_at_frame < before.expires_at_frame:
            raise ValueError("雷暴云刷新不能缩短 expires_at_frame")
        if before.revision <= 0:
            raise ValueError("雷暴云 revision 必须为正整数")
        state = LunarStormCloudState(
            instance_ref=before.instance_ref,
            subject_ref=before.subject_ref,
            space_entity_ref=before.space_entity_ref,
            created_by_occurrence_ref=before.created_by_occurrence_ref,
            trigger_source_ref=before.trigger_source_ref,
            team_ref=before.team_ref,
            created_frame=before.created_frame,
            expires_at_frame=expires_at_frame,
            next_attack_frame=before.next_attack_frame,
            next_attack_index=before.next_attack_index,
            attack_interval_frames=before.attack_interval_frames,
            revision=before.revision + 1,
        )
        self._working[state.slot_key] = state
        return state

    def replace_lunar_storm_cloud_attack(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
        next_attack_frame: int,
        next_attack_index: int,
    ) -> LunarStormCloudState:
        """攻击帧规范化时推进攻击游标，不改变存在时间与触发来源。"""

        self._assert_open()
        before = self.lunar_storm_cloud_for(instance_ref)
        if before is None:
            raise ValueError("不存在可推进的 LunarStormCloudState")
        _frame(next_attack_frame, "next_attack_frame")
        if next_attack_frame <= before.next_attack_frame:
            raise ValueError("雷暴云攻击游标不能回退")
        _frame(next_attack_index, "next_attack_index")
        if next_attack_index != before.next_attack_index + 1:
            raise ValueError("雷暴云攻击 index 必须连续递增")
        state = LunarStormCloudState(
            instance_ref=before.instance_ref,
            subject_ref=before.subject_ref,
            space_entity_ref=before.space_entity_ref,
            created_by_occurrence_ref=before.created_by_occurrence_ref,
            trigger_source_ref=before.trigger_source_ref,
            team_ref=before.team_ref,
            created_frame=before.created_frame,
            expires_at_frame=before.expires_at_frame,
            next_attack_frame=next_attack_frame,
            next_attack_index=next_attack_index,
            attack_interval_frames=before.attack_interval_frames,
            revision=before.revision + 1,
        )
        self._working[state.slot_key] = state
        return state

    def remove_lunar_storm_cloud(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarStormCloudState:
        self._assert_open()
        before = self.lunar_storm_cloud_for(instance_ref)
        if before is None:
            raise ValueError("不存在可终结的 LunarStormCloudState")
        del self._working[before.slot_key]
        return before

    def create_lunar_cage(
        self,
        intent: object,
        *,
        index: int,
    ) -> LunarCageState:
        """接受月结晶声明的确定性月笼创建意图。"""

        from genshin_sim.core.systems.reaction.models import (
            LunarCrystallizeStatePlanningIntent,
        )

        self._assert_open()
        if not isinstance(intent, LunarCrystallizeStatePlanningIntent):
            raise ValueError("intent 必须是 LunarCrystallizeStatePlanningIntent")
        if intent.created_frame != self.frame:
            raise ValueError("月笼创建意图帧必须与 State 批次一致")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 3:
            raise ValueError("月笼创建序号必须位于 0~2")
        instance_ref = intent.cage_instance_refs[index]
        if self.lunar_cage_for(instance_ref) is not None:
            raise ValueError("月笼 instance_ref 已存在")
        state = LunarCageState(
            instance_ref=instance_ref,
            subject_ref=intent.subject_ref,
            space_entity_ref=intent.cage_space_entity_refs[index],
            created_by_occurrence_ref=intent.parent_occurrence_ref,
            trigger_source_ref=intent.trigger_source_ref,
            team_ref=intent.team_ref,
            created_frame=intent.created_frame,
            last_harmony_frame=intent.created_frame,
            next_attack_frame=intent.created_frame,
            expires_at_frame=intent.created_frame + 540,
            attack_index=0,
        )
        if state.slot_key in self._working:
            raise ValueError("月笼 State slot 已存在")
        self._working[state.slot_key] = state
        return state

    def remove_lunar_cage(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarCageState:
        self._assert_open()
        before = self.lunar_cage_for(instance_ref)
        if before is None:
            raise ValueError("不存在可终结的 LunarCageState")
        del self._working[before.slot_key]
        return before

    def replace_lunar_cage_after_harmony(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
        frame: int,
    ) -> LunarCageState:
        """月笼发射谐奏后推进冷却游标并刷新 9 秒存活窗口。"""

        self._assert_open()
        before = self.lunar_cage_for(instance_ref)
        if before is None:
            raise ValueError("不存在可发射的 LunarCageState")
        _frame(frame, "frame")
        if frame < before.next_attack_frame:
            raise ValueError("月笼投射物冷却尚未结束")
        state = LunarCageState(
            instance_ref=before.instance_ref,
            subject_ref=before.subject_ref,
            space_entity_ref=before.space_entity_ref,
            created_by_occurrence_ref=before.created_by_occurrence_ref,
            trigger_source_ref=before.trigger_source_ref,
            team_ref=before.team_ref,
            created_frame=before.created_frame,
            last_harmony_frame=frame,
            next_attack_frame=frame + 21,
            expires_at_frame=frame + 540,
            attack_index=before.attack_index + 1,
            revision=before.revision + 1,
        )
        self._working[state.slot_key] = state
        return state

    def append_lunar_crystallize_record(
        self,
        *,
        team_ref: str,
        subject_ref: ElementalSubjectRef,
        record: LunarCrystallizeOccurrenceRecord,
    ) -> LunarCrystallizeAccumulatorState:
        """追加 occurrence 记录；超过 4 层时丢弃最旧记录。"""

        self._assert_open()
        if not isinstance(team_ref, str) or not team_ref.strip():
            raise ValueError("team_ref 必须是非空字符串")
        if not isinstance(subject_ref, ElementalSubjectRef):
            raise ValueError("subject_ref 必须是 ElementalSubjectRef")
        if not isinstance(record, LunarCrystallizeOccurrenceRecord):
            raise ValueError("record 必须是 LunarCrystallizeOccurrenceRecord")
        before = self.lunar_crystallize_accumulator_for(team_ref)
        if before is None:
            pending = (record,)
            anchor = subject_ref
            revision = 1
        else:
            pending = (*before.pending_records, record)
            anchor = before.subject_ref
            revision = before.revision + 1
        if len(pending) > 4:
            pending = pending[-4:]
        state = LunarCrystallizeAccumulatorState(
            instance_ref=ReactionStateInstanceRef(
                f"reaction-state:lunar-crystallize-accumulator:{team_ref}"
            ),
            team_ref=team_ref,
            subject_ref=anchor,
            pending_records=pending,
            max_layers=4,
            revision=revision,
        )
        self._working[state.slot_key] = state
        return state

    def consume_lunar_crystallize_records(
        self,
        *,
        team_ref: str,
        count: int = 3,
    ) -> tuple[
        tuple[LunarCrystallizeOccurrenceRecord, ...],
        LunarCrystallizeAccumulatorState | None,
    ]:
        """消费前 count 条记录；全部消费后移除累计器状态。"""

        self._assert_open()
        if not isinstance(team_ref, str) or not team_ref.strip():
            raise ValueError("team_ref 必须是非空字符串")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("count 必须是正整数")
        before = self.lunar_crystallize_accumulator_for(team_ref)
        if before is None or len(before.pending_records) < count:
            raise ValueError("月结晶累计器记录不足")
        consumed = before.pending_records[:count]
        remaining = before.pending_records[count:]
        if not remaining:
            del self._working[before.slot_key]
            return consumed, None
        state = LunarCrystallizeAccumulatorState(
            instance_ref=before.instance_ref,
            team_ref=before.team_ref,
            subject_ref=before.subject_ref,
            pending_records=remaining,
            max_layers=before.max_layers,
            revision=before.revision + 1,
        )
        self._working[state.slot_key] = state
        return consumed, state

    def create_sprawling_shot(self, state: SprawlingShotState) -> SprawlingShotState:
        self._assert_open()
        if not isinstance(state, SprawlingShotState):
            raise ValueError("state 必须是 SprawlingShotState")
        if state.created_frame != self.frame:
            raise ValueError("蔓生弹创建帧必须与 State 批次一致")
        if self.sprawling_shot_for(state.instance_ref) is not None:
            raise ValueError("蔓生弹 instance_ref 已存在")
        if state.slot_key in self._working:
            raise ValueError("蔓生弹 State slot 已存在")
        self._working[state.slot_key] = state
        return state

    def remove_sprawling_shot(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
    ) -> SprawlingShotState:
        self._assert_open()
        before = self.sprawling_shot_for(instance_ref)
        if before is None:
            raise ValueError("不存在可终结的 SprawlingShotState")
        del self._working[before.slot_key]
        return before

    def terminalize_crystallize_shard(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
        lifecycle_state: CrystallizeShardLifecycleState,
    ) -> CrystallizeShardState:
        self._assert_open()
        if lifecycle_state not in {
            CrystallizeShardLifecycleState.PICKED,
            CrystallizeShardLifecycleState.EXPIRED,
        }:
            raise ValueError("晶片终态必须是 picked 或 expired")
        before = self.crystallize_shard_for(instance_ref)
        if before is None:
            raise ValueError("不存在可终结的 CrystallizeShardState")
        if before.lifecycle_state is not CrystallizeShardLifecycleState.ACTIVE:
            raise ValueError("CrystallizeShardState 已经处于终态")
        if lifecycle_state is CrystallizeShardLifecycleState.PICKED and not (
            before.created_frame <= self.frame < before.expires_at_frame
        ):
            raise ValueError("晶片拾取帧必须处于活动区间")
        if lifecycle_state is CrystallizeShardLifecycleState.EXPIRED and (
            self.frame != before.expires_at_frame
        ):
            raise ValueError("晶片到期终态必须在 expires_at_frame 执行")
        state = replace(
            before,
            lifecycle_state=lifecycle_state,
            terminal_frame=self.frame,
            revision=before.revision + 1,
        )
        self._working[state.slot_key] = state
        return state

    def replace_frozen(self, state: FrozenState) -> FrozenState:
        self._assert_open()
        if not isinstance(state, FrozenState):
            raise ValueError("replace_frozen 只接受 FrozenState")
        before = self._working.get(state.slot_key)
        if not isinstance(before, FrozenState):
            raise ValueError("不存在可替换的 FrozenState")
        if state.instance_ref != before.instance_ref:
            raise ValueError("FrozenState 刷新必须保留实例引用")
        if state.created_frame != before.created_frame:
            raise ValueError("FrozenState 刷新必须保留创建帧")
        self._working[state.slot_key] = state
        return state

    def replace_freeze_recovery(
        self,
        state: FreezeRecoveryState,
    ) -> FreezeRecoveryState:
        self._assert_open()
        if not isinstance(state, FreezeRecoveryState):
            raise ValueError("replace_freeze_recovery 只接受 FreezeRecoveryState")
        before = self._working.get(state.slot_key)
        if not isinstance(before, FreezeRecoveryState):
            raise ValueError("不存在可替换的 FreezeRecoveryState")
        if state.instance_ref != before.instance_ref:
            raise ValueError("FreezeRecoveryState 刷新必须保留实例引用")
        self._working[state.slot_key] = state
        return state

    def replace_electro_charged(
        self,
        state: ElectroChargedState,
    ) -> ElectroChargedState:
        self._assert_open()
        if not isinstance(state, ElectroChargedState):
            raise ValueError("replace_electro_charged 只接受 ElectroChargedState")
        before = self._working.get(state.slot_key)
        if not isinstance(before, ElectroChargedState):
            raise ValueError("不存在可替换的 ElectroChargedState")
        if state.instance_ref != before.instance_ref:
            raise ValueError("ElectroChargedState 刷新必须保留实例引用")
        if state.created_frame != before.created_frame:
            raise ValueError("ElectroChargedState 刷新必须保留创建帧")
        if state.revision <= before.revision:
            raise ValueError("ElectroChargedState 替换必须递增 revision")
        self._working[state.slot_key] = state
        return state

    def replace_burning(self, state: BurningState) -> BurningState:
        self._assert_open()
        if not isinstance(state, BurningState):
            raise ValueError("replace_burning 只接受 BurningState")
        before = self._working.get(state.slot_key)
        if not isinstance(before, BurningState):
            raise ValueError("不存在可替换的 BurningState")
        if state.instance_ref != before.instance_ref:
            raise ValueError("BurningState 刷新必须保留实例引用")
        if state.subject_ref != before.subject_ref:
            raise ValueError("BurningState 刷新必须保留主体")
        if state.burning_aura_link_ref != before.burning_aura_link_ref:
            raise ValueError("BurningState 刷新必须保留燃元素 Link")
        if state.burning_aura_link_ref not in state.dendro_like_link_refs:
            raise ValueError("BurningState 刷新后的类草 Link 必须保留 Burning Link")
        if state.created_by_occurrence_ref != before.created_by_occurrence_ref:
            raise ValueError("BurningState 刷新必须保留创建 occurrence")
        if state.created_frame != before.created_frame:
            raise ValueError("BurningState 刷新必须保留创建帧")
        if state.revision <= before.revision:
            raise ValueError("BurningState 替换必须递增 revision")
        if (
            state.next_damage_tick_frame < before.next_damage_tick_frame
            or state.next_damage_tick_index < before.next_damage_tick_index
            or state.next_pyro_application_frame < before.next_pyro_application_frame
            or state.next_pyro_application_index < before.next_pyro_application_index
        ):
            raise ValueError("BurningState 替换不能回退周期 cursor")
        self._working[state.slot_key] = state
        return state

    def replace_quicken(self, state: QuickenState) -> QuickenState:
        self._assert_open()
        if not isinstance(state, QuickenState):
            raise ValueError("replace_quicken 只接受 QuickenState")
        before = self._working.get(state.slot_key)
        if not isinstance(before, QuickenState):
            raise ValueError("不存在可替换的 QuickenState")
        if state.instance_ref != before.instance_ref:
            raise ValueError("QuickenState 刷新必须保留实例引用")
        if state.subject_ref != before.subject_ref:
            raise ValueError("QuickenState 刷新必须保留主体")
        if state.quicken_aura_link_ref != before.quicken_aura_link_ref:
            raise ValueError("QuickenState 刷新必须保留激元素 Link")
        if state.created_by_occurrence_ref != before.created_by_occurrence_ref:
            raise ValueError("QuickenState 刷新必须保留创建 occurrence")
        if state.created_frame != before.created_frame:
            raise ValueError("QuickenState 刷新必须保留创建帧")
        if state.revision <= before.revision:
            raise ValueError("QuickenState 替换必须递增 revision")
        self._working[state.slot_key] = state
        return state

    def remove_frozen(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        expected_instance_ref: ReactionStateInstanceRef | None = None,
    ) -> FrozenState:
        self._assert_open()
        key = ReactionStateSlotKey(subject_ref, ReactionStateSlot.FROZEN)
        before = self._working.get(key)
        if not isinstance(before, FrozenState):
            raise ValueError("不存在可移除的 FrozenState")
        if expected_instance_ref is not None and before.instance_ref != expected_instance_ref:
            raise ValueError("FrozenState 实例前值冲突")
        del self._working[key]
        return before

    def remove_freeze_recovery(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        expected_instance_ref: ReactionStateInstanceRef | None = None,
    ) -> FreezeRecoveryState:
        self._assert_open()
        key = ReactionStateSlotKey(subject_ref, ReactionStateSlot.FREEZE_RECOVERY)
        before = self._working.get(key)
        if not isinstance(before, FreezeRecoveryState):
            raise ValueError("不存在可移除的 FreezeRecoveryState")
        if expected_instance_ref is not None and before.instance_ref != expected_instance_ref:
            raise ValueError("FreezeRecoveryState 实例前值冲突")
        del self._working[key]
        return before

    def remove_electro_charged(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        expected_instance_ref: ReactionStateInstanceRef | None = None,
    ) -> ElectroChargedState:
        self._assert_open()
        key = ReactionStateSlotKey(subject_ref, ReactionStateSlot.ELECTRO_CHARGED)
        before = self._working.get(key)
        if not isinstance(before, ElectroChargedState):
            raise ValueError("不存在可移除的 ElectroChargedState")
        if expected_instance_ref is not None and before.instance_ref != expected_instance_ref:
            raise ValueError("ElectroChargedState 实例前值冲突")
        del self._working[key]
        return before

    def remove_burning(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        expected_instance_ref: ReactionStateInstanceRef | None = None,
    ) -> BurningState:
        self._assert_open()
        key = ReactionStateSlotKey(subject_ref, ReactionStateSlot.BURNING)
        before = self._working.get(key)
        if not isinstance(before, BurningState):
            raise ValueError("不存在可移除的 BurningState")
        if expected_instance_ref is not None and before.instance_ref != expected_instance_ref:
            raise ValueError("BurningState 实例前值冲突")
        del self._working[key]
        return before

    def remove_quicken(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        expected_instance_ref: ReactionStateInstanceRef | None = None,
    ) -> QuickenState:
        self._assert_open()
        key = ReactionStateSlotKey(subject_ref, ReactionStateSlot.QUICKEN)
        before = self._working.get(key)
        if not isinstance(before, QuickenState):
            raise ValueError("不存在可移除的 QuickenState")
        if expected_instance_ref is not None and before.instance_ref != expected_instance_ref:
            raise ValueError("QuickenState 实例前值冲突")
        del self._working[key]
        return before

    def seal(self) -> ReactionStateMutationPlan:
        self._assert_open()
        self._sealed = True
        keys = tuple(sorted(set(self._original) | set(self._working)))
        changes = tuple(
            ReactionStateChange(key, self._original.get(key), self._working.get(key))
            for key in keys
            if self._original.get(key) != self._working.get(key)
        )
        return ReactionStateMutationPlan(
            operation_id=f"reaction-state:{self.batch_id}",
            frame=self.frame,
            expected_store_version=self._expected_store_version,
            expected_records=tuple(
                change.before for change in changes if change.before is not None
            ),
            replacement_records=tuple(
                change.after for change in changes if change.after is not None
            ),
            removed_slot_keys=tuple(change.slot_key for change in changes if change.after is None),
            changes=changes,
            next_state_instance_sequence=self._instance_sequence,
            next_dendro_core_creation_sequence=self._dendro_core_creation_sequence,
        )

    def _assert_open(self) -> None:
        if self._sealed:
            raise RuntimeError("ReactionStatePlanner 已封存")

    def _next_instance_ref(self) -> str:
        self._instance_sequence += 1
        return f"reaction-state-instance:{self._instance_sequence}"
