"""星超导极星辉域与队伍共享计数的跨领域创建/记录计划。

该模块是星超导写协调的 Reaction 侧窄入口：只组合 ReactionState、Space
与领域条件证据，形成确定性计划，不拥有长期状态，不推进结算周期。
辉映·星超导 Buff 的统一创建/刷新/移除由后续 Buff 系统接线承担。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from genshin_sim.core.coordination.elemental_reaction.protocols import (
    ReactionSpatialBatchPlanningPort,
    ReactionStateBatchPlanningPort,
)
from genshin_sim.core.entity_states import EntityLifecycle
from genshin_sim.core.space import SpatialEntity
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_FIELD_RADIUS,
)
from genshin_sim.core.systems.reaction.models import (
    PolestarFieldStatePlanningIntent,
    SpatialEntityCreationEffect,
)
from genshin_sim.core.systems.reaction.states import (
    PolestarFieldState,
    ReactionStateInstanceRef,
    StellarConductAttachmentRecord,
    StellarConductCounterState,
)


class StellarConductPlanningError(RuntimeError):
    """极星辉域 State 与 Space 投影不能完成创建或刷新计划。"""


class StellarConductAttachmentRecordingOutcome(StrEnum):
    """一次附着记录请求的确定性结果。"""

    RECORDED = "recorded"
    NO_ACTIVE_SESSION = "no_active_session"
    FIELD_EXPIRED = "field_expired"
    EXCLUDED_ATTACK = "excluded_attack"
    DUPLICATE_RECORD = "duplicate_record"
    TARGETS_OUTSIDE_FIELD = "targets_outside_field"


class PolestarFieldPlanOutcome(StrEnum):
    """一次星超导 occurrence 对极星辉域的确定性处置。"""

    CREATED = "created"
    REFRESHED = "refreshed"
    REPLACED = "replaced"


@dataclass(frozen=True, slots=True)
class PolestarFieldPlanResult:
    outcome: PolestarFieldPlanOutcome
    removed_field_instance_ref: ReactionStateInstanceRef | None = None

    @property
    def created(self) -> bool:
        return self.outcome is PolestarFieldPlanOutcome.CREATED

    @property
    def refreshed(self) -> bool:
        return self.outcome is not PolestarFieldPlanOutcome.CREATED

    def __post_init__(self) -> None:
        if self.outcome is PolestarFieldPlanOutcome.REPLACED:
            if self.removed_field_instance_ref is None:
                raise ValueError("域外替换必须声明被移除的旧领域实例")
        elif self.removed_field_instance_ref is not None:
            raise ValueError("只有域外替换会移除旧领域")


@dataclass(frozen=True, slots=True)
class StellarConductAttachmentRecording:
    counter: StellarConductCounterState | None
    outcome: StellarConductAttachmentRecordingOutcome

    @property
    def recorded(self) -> bool:
        return self.outcome is StellarConductAttachmentRecordingOutcome.RECORDED


def plan_polestar_field_occurrence(
    *,
    context: Any,
    state_planner: ReactionStateBatchPlanningPort,
    spatial_planner: ReactionSpatialBatchPlanningPort,
    intent: PolestarFieldStatePlanningIntent,
    spatial_effect: SpatialEntityCreationEffect,
) -> PolestarFieldPlanResult:
    """域内重触发只刷新领域时间并同步 Space 投影；域外重触发替换旧领域并继承共享计数。

    领域圆心固定在触发反应的敌人当时位置，与角色位置无关；同一队伍
    至多存在一个极星辉域。队伍共享计数不绑定 Field 实例，领域替换时
    继续继承 4 秒窗口，只有会话首次创建才写入排除的触发攻击身份。
    域内刷新保留实例、圆心与创建帧，同步延展 State 与 Space 实体的
    存在时间，避免空间投影提前失活。
    """

    if context.space_runtime is None:
        raise StellarConductPlanningError("极星辉域计划缺少 SpaceRuntime")
    anchor = context.space_runtime.get_entity(intent.subject_ref.entity_id)
    if anchor is None:
        raise StellarConductPlanningError("极星辉域计划缺少主体空间锚点")
    existing = _require_unique_field(state_planner, intent.team_ref)

    if existing is None:
        state_planner.create_polestar_field(intent)
        _ensure_counter_for_creation(state_planner, intent)
        spatial_planner.prepare_create(spatial_effect, anchor=anchor)
        return PolestarFieldPlanResult(PolestarFieldPlanOutcome.CREATED)

    entity = _field_space_entity(context, spatial_planner, existing)
    distance = entity.position.distance_xz_to(anchor.position)
    if distance <= STELLAR_CONDUCT_FIELD_RADIUS:
        state_planner.replace_polestar_field(
            instance_ref=existing.instance_ref,
            expires_at_frame=intent.expires_at_frame,
        )
        spatial_planner.prepare_update(
            replace(
                entity,
                lifecycle=EntityLifecycle(
                    created_frame=entity.lifecycle.created_frame,
                    expires_at_frame=intent.expires_at_frame,
                ),
            )
        )
        return PolestarFieldPlanResult(PolestarFieldPlanOutcome.REFRESHED)

    removed_ref = existing.instance_ref
    state_planner.remove_polestar_field(instance_ref=removed_ref)
    if context.space_runtime.get_entity(existing.space_entity_ref) is not None:
        spatial_planner.prepare_remove(existing.space_entity_ref)
    else:
        spatial_planner.cancel_create(existing.space_entity_ref)
    state_planner.create_polestar_field(intent)
    if intent.excluded_attack_ref is not None:
        state_planner.replace_stellar_conduct_counter_exclusions(
            team_ref=intent.team_ref,
            excluded_attack_refs=(intent.excluded_attack_ref,),
        )
    spatial_planner.prepare_create(spatial_effect, anchor=anchor)
    return PolestarFieldPlanResult(
        PolestarFieldPlanOutcome.REPLACED,
        removed_field_instance_ref=removed_ref,
    )


def record_stellar_conduct_attachment(
    *,
    context: Any,
    state_planner: ReactionStateBatchPlanningPort,
    team_ref: str,
    record: StellarConductAttachmentRecord,
    spatial_planner: ReactionSpatialBatchPlanningPort | None = None,
) -> StellarConductAttachmentRecording:
    """按队伍共享规则记录一次领域内冰/雷附着；不满足条件时给出确定性结果。

    一次攻击对多个敌人的附着由调用方聚合为一条记录；同一 record_ref
    重放、被排除的触发攻击与领域外目标都不会推进窗口层数。
    领域可能在本批次内刚创建：调用方持有未提交的空间批次时必须把
    ``spatial_planner`` 一并传入，否则无法读取同批次创建的领域投影。
    """

    if context.space_runtime is None:
        raise StellarConductPlanningError("星超导附着记录缺少 SpaceRuntime")
    counter = state_planner.stellar_conduct_counter_for(team_ref)
    if counter is None:
        return StellarConductAttachmentRecording(
            None, StellarConductAttachmentRecordingOutcome.NO_ACTIVE_SESSION
        )
    field = _require_unique_field(state_planner, team_ref)
    if field is None or field.expires_at_frame <= record.frame:
        return StellarConductAttachmentRecording(
            counter, StellarConductAttachmentRecordingOutcome.FIELD_EXPIRED
        )
    if record.attack_ref in counter.excluded_attack_refs:
        return StellarConductAttachmentRecording(
            counter, StellarConductAttachmentRecordingOutcome.EXCLUDED_ATTACK
        )
    if record.record_ref in counter.recorded_record_refs:
        return StellarConductAttachmentRecording(
            counter, StellarConductAttachmentRecordingOutcome.DUPLICATE_RECORD
        )
    center = _field_space_entity(context, spatial_planner, field).position
    for target_ref in record.target_refs:
        entity = context.space_runtime.get_entity(target_ref.entity_id)
        if entity is not None and entity.position.distance_xz_to(center) <= (
            STELLAR_CONDUCT_FIELD_RADIUS
        ):
            updated = state_planner.append_stellar_conduct_attachment_record(
                team_ref=team_ref,
                record=record,
            )
            return StellarConductAttachmentRecording(
                updated, StellarConductAttachmentRecordingOutcome.RECORDED
            )
    return StellarConductAttachmentRecording(
        counter, StellarConductAttachmentRecordingOutcome.TARGETS_OUTSIDE_FIELD
    )


def _require_unique_field(
    state_planner: ReactionStateBatchPlanningPort,
    team_ref: str,
) -> PolestarFieldState | None:
    fields = state_planner.active_polestar_fields(team_ref=team_ref)
    if len(fields) > 1:
        raise StellarConductPlanningError("同一队伍同时存在多个极星辉域")
    return fields[0] if fields else None


def _field_space_entity(
    context: Any,
    spatial_planner: ReactionSpatialBatchPlanningPort | None,
    field: PolestarFieldState,
) -> SpatialEntity:
    entity = context.space_runtime.get_entity(field.space_entity_ref)
    if entity is None and spatial_planner is not None:
        entity = next(
            (
                receipt.entity
                for receipt in spatial_planner.creation_receipts
                if receipt.entity.entity_id == field.space_entity_ref
            ),
            None,
        )
    if entity is None:
        raise StellarConductPlanningError("极星辉域 State 缺少 Space 投影")
    return entity


def _ensure_counter_for_creation(
    state_planner: ReactionStateBatchPlanningPort,
    intent: PolestarFieldStatePlanningIntent,
) -> None:
    counter = state_planner.stellar_conduct_counter_for(intent.team_ref)
    if counter is None:
        state_planner.create_stellar_conduct_counter(
            team_ref=intent.team_ref,
            subject_ref=intent.subject_ref,
            frame=intent.created_frame,
            excluded_attack_refs=(
                (intent.excluded_attack_ref,) if intent.excluded_attack_ref is not None else ()
            ),
        )
        return
    if intent.excluded_attack_ref is not None:
        state_planner.replace_stellar_conduct_counter_exclusions(
            team_ref=intent.team_ref,
            excluded_attack_refs=(intent.excluded_attack_ref,),
        )
