"""星超导辉映 Buff 与极星辉域来源物理减抗的跨系统计划。

该模块是星超导写协调的 Buff 侧窄入口：只依据 ReactionState 批次内已计划
的领域与计数快照，生成确定性的 Buff 申请与移除请求，不拥有长期状态。
辉映·星烁 Buff 是共享会话在角色侧的投影；极星辉域来源的物理减抗复用
普通超导的 Buff Definition 与 conflict slot，同一目标不叠加为 ``-80%``。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from genshin_sim.core.attributes import (
    BONUS_DAMAGE_CRYO,
    BONUS_DAMAGE_ELECTRO,
    STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.coordination.elemental_reaction.status import (
    SUPERCONDUCT_BUFF_DEFINITION_KEY,
    SUPERCONDUCT_BUFF_TERM_KEY,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_conduct import (
    StellarConductPlanningError,
    field_space_entity,
)
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffModifierValue,
    BuffValueRefreshPolicy,
    RemoveBuffRequest,
)
from genshin_sim.core.systems.buff.enums import BuffRemovalReason
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_FIELD_RADIUS,
    STELLAR_CONDUCT_TEAM_SCOPE,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.mechanic import (
    stellar_conduct_direct_multiplier,
    stellar_conduct_elemental_bonus,
)
from genshin_sim.core.systems.reaction.states import PolestarFieldState

STELLAR_RADIANCE_BUFF_DEFINITION_KEY = "buff.reaction.stellar_conduct.radiance"
STELLAR_RADIANCE_BUFF_MECHANIC_KEY = "reaction.stellar_conduct"
STELLAR_RADIANCE_BUFF_HANDLER_KEY = "reaction_handler.stellar_conduct.radiance"
STELLAR_RADIANCE_BUFF_CONFLICT_KEY = "buff_conflict.reaction.stellar_conduct.radiance"
STELLAR_RADIANCE_CRYO_BONUS_TERM_KEY = "stellar.conduct.radiance.cryo_bonus"
STELLAR_RADIANCE_ELECTRO_BONUS_TERM_KEY = "stellar.conduct.radiance.electro_bonus"
STELLAR_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY = "stellar.conduct.radiance.direct_base_multiplier"
# 领域消失后辉映·星烁 Buff 的自然延续基线（约 1 秒，60 帧）；精确帧边界待来源化冻结。
STELLAR_RADIANCE_PERSISTENCE_FRAMES = 60
# 极星辉域来源物理减抗在 source_context 中的稳定 key，用于与普通超导来源区分。
STELLAR_FIELD_RESIST_SOURCE_KEY = "reaction.stellar_conduct.polestar_field"
# 与普通超导状态效果相同的物理抗性降低值。
STELLAR_FIELD_RESISTANCE_REDUCTION = -0.40


def stellar_radiance_buff_definition() -> BuffDefinition:
    """辉映·星烁 Buff：共享会话的角色侧投影，携带冰/雷增伤与直伤系数证据。"""

    return BuffDefinition(
        definition_key=STELLAR_RADIANCE_BUFF_DEFINITION_KEY,
        mechanic_key=STELLAR_RADIANCE_BUFF_MECHANIC_KEY,
        handler_key=STELLAR_RADIANCE_BUFF_HANDLER_KEY,
        conflict_key=STELLAR_RADIANCE_BUFF_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=STELLAR_RADIANCE_CRYO_BONUS_TERM_KEY,
                target_key=BONUS_DAMAGE_CRYO,
                stage=ModifierStage.FLAT_ADD,
            ),
            BuffAttributeModifierTemplate(
                term_key=STELLAR_RADIANCE_ELECTRO_BONUS_TERM_KEY,
                target_key=BONUS_DAMAGE_ELECTRO,
                stage=ModifierStage.FLAT_ADD,
            ),
            BuffAttributeModifierTemplate(
                term_key=STELLAR_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY,
                target_key=STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({STELLAR_RADIANCE_BUFF_MECHANIC_KEY}),
        display_name="辉映·星超导",
    )


@dataclass(frozen=True, slots=True)
class StellarConductBuffChangePlan:
    """一次星超导触发需要提交的 Buff 申请与移除请求。"""

    apply_requests: tuple[ApplyBuffRequest, ...] = ()
    remove_requests: tuple[RemoveBuffRequest, ...] = ()


def plan_radiance_buff_requests(
    *,
    frame: int,
    occurrence_ref: str,
    character_refs: Sequence[AttributeSubjectRef],
    settled_stacks: int,
    field_expires_at_frame: int,
    order_start: int = 0,
) -> tuple[ApplyBuffRequest, ...]:
    """为队伍角色生成统一刷新的辉映·星烁 Buff 申请。

    Buff 的存在时间始终覆盖领域剩余时间并自然延续
    ``STELLAR_RADIANCE_PERSISTENCE_FRAMES`` 帧；数值来自当前结算层数快照，
    由协调器在触发与 4 秒周期结算时统一刷新。
    """

    duration_frames = field_expires_at_frame + STELLAR_RADIANCE_PERSISTENCE_FRAMES - frame
    if duration_frames <= 0:
        raise StellarConductPlanningError("辉映·星烁 Buff 的存续时间必须为正数")
    cryo_bonus = stellar_conduct_elemental_bonus(settled_stacks)
    electro_bonus = stellar_conduct_elemental_bonus(settled_stacks)
    direct_multiplier = stellar_conduct_direct_multiplier(settled_stacks)
    source_context = RuntimeSourceRef(
        RuntimeSourceKind.MECHANIC,
        STELLAR_RADIANCE_BUFF_MECHANIC_KEY,
        STELLAR_CONDUCT_TEAM_SCOPE,
    )
    ordered_refs = sorted(character_refs, key=lambda item: item.entity_id)
    return tuple(
        ApplyBuffRequest(
            request_id=f"{occurrence_ref}:stellar-radiance:{ref.entity_id}",
            frame=frame,
            order=order_start + order,
            definition_key=STELLAR_RADIANCE_BUFF_DEFINITION_KEY,
            target_ref=ref,
            source_context=source_context,
            duration_frames=duration_frames,
            modifier_values=(
                BuffModifierValue(STELLAR_RADIANCE_CRYO_BONUS_TERM_KEY, cryo_bonus),
                BuffModifierValue(STELLAR_RADIANCE_ELECTRO_BONUS_TERM_KEY, electro_bonus),
                BuffModifierValue(STELLAR_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY, direct_multiplier),
            ),
        )
        for order, ref in enumerate(ordered_refs)
    )


def plan_stellar_conduct_buff_changes(
    *,
    context: Any,
    buff_port: Any,
    state_planner: Any,
    frame: int,
    occurrence_ref: str,
    spatial_planner: Any = None,
) -> StellarConductBuffChangePlan:
    """按批次内已计划的领域与计数快照，生成 Buff 申请与移除请求。

    队伍每个角色统一获得或刷新辉映·星烁 Buff；领域内敌人获得极星辉域
    来源的物理减抗（复用普通超导 Definition 与 conflict slot），持有领域
    来源减抗但已离开领域的敌人被显式移除。所有请求在同一批次内原子提交。
    """

    if context.space_runtime is None:
        raise StellarConductPlanningError("星超导 Buff 计划缺少 SpaceRuntime")
    if buff_port is None:
        raise StellarConductPlanningError("星超导 Buff 计划缺少 Buff 规划端口")
    fields = state_planner.active_polestar_fields(team_ref=STELLAR_CONDUCT_TEAM_SCOPE)
    if len(fields) != 1:
        raise StellarConductPlanningError("星超导 Buff 计划要求当前队伍恰好一个极星辉域")
    field = fields[0]
    counter = state_planner.stellar_conduct_counter_for(STELLAR_CONDUCT_TEAM_SCOPE)
    if counter is None:
        raise StellarConductPlanningError("星超导 Buff 计划缺少队伍共享计数")
    center = field_space_entity(context, spatial_planner, field).position

    character_refs = tuple(
        AttributeSubjectRef.character(character.combat_entity_id)
        for character in context.space_runtime.team_state.characters
    )
    apply_requests: list[ApplyBuffRequest] = list(
        plan_radiance_buff_requests(
            frame=frame,
            occurrence_ref=occurrence_ref,
            character_refs=character_refs,
            settled_stacks=counter.settled_stacks,
            field_expires_at_frame=field.expires_at_frame,
        )
    )

    enemy_positions = _enemy_positions(context)
    inside_refs = {
        entity_id
        for entity_id, position in enemy_positions
        if position.distance_xz_to(center) <= STELLAR_CONDUCT_FIELD_RADIUS
    }
    resist_order_start = len(apply_requests)
    for order, (entity_id, _) in enumerate(sorted(enemy_positions, key=lambda item: item[0])):
        if entity_id in inside_refs:
            apply_requests.append(
                _field_resistance_apply_request(
                    frame=frame,
                    occurrence_ref=occurrence_ref,
                    entity_id=entity_id,
                    field=field,
                    order=resist_order_start + order,
                )
            )
    remove_requests = _stale_field_resistance_removals(
        frame=frame,
        occurrence_ref=occurrence_ref,
        buff_port=buff_port,
        inside_refs=inside_refs,
        enemy_entity_ids={entity_id for entity_id, _ in enemy_positions},
    )
    return StellarConductBuffChangePlan(
        apply_requests=tuple(apply_requests),
        remove_requests=remove_requests,
    )


def _field_resistance_apply_request(
    *,
    frame: int,
    occurrence_ref: str,
    entity_id: str,
    field: PolestarFieldState,
    order: int,
) -> ApplyBuffRequest:
    duration_frames = field.expires_at_frame - frame
    if duration_frames <= 0:
        raise StellarConductPlanningError("极星辉域减抗 Buff 的存续时间必须为正数")
    return ApplyBuffRequest(
        request_id=f"{occurrence_ref}:stellar-field-resist:{entity_id}",
        frame=frame,
        order=order,
        definition_key=SUPERCONDUCT_BUFF_DEFINITION_KEY,
        target_ref=AttributeSubjectRef.target(entity_id),
        source_context=RuntimeSourceRef(
            RuntimeSourceKind.MECHANIC,
            STELLAR_FIELD_RESIST_SOURCE_KEY,
            field.instance_ref.value,
        ),
        duration_frames=duration_frames,
        modifier_values=(
            BuffModifierValue(SUPERCONDUCT_BUFF_TERM_KEY, STELLAR_FIELD_RESISTANCE_REDUCTION),
        ),
    )


def _stale_field_resistance_removals(
    *,
    frame: int,
    occurrence_ref: str,
    buff_port: Any,
    inside_refs: frozenset[str] | set[str],
    enemy_entity_ids: set[str],
) -> tuple[RemoveBuffRequest, ...]:
    """移除已离开领域的敌人身上的领域来源减抗；普通超导来源不受影响。"""

    removals: list[RemoveBuffRequest] = []
    for record in buff_port.reader.active(frame, definition_key=SUPERCONDUCT_BUFF_DEFINITION_KEY):
        source_context = record.state.source_context
        if source_context.kind is not RuntimeSourceKind.MECHANIC:
            continue
        if source_context.source_key != STELLAR_FIELD_RESIST_SOURCE_KEY:
            continue
        target_ref = record.state.target_ref
        if target_ref.kind is not AttributeSubjectKind.TARGET:
            continue
        if target_ref.entity_id in inside_refs:
            continue
        if target_ref.entity_id not in enemy_entity_ids:
            continue
        removals.append(
            RemoveBuffRequest(
                request_id=f"{occurrence_ref}:stellar-field-resist-remove:{target_ref.entity_id}",
                frame=frame,
                instance_ref=record.instance_ref,
                reason=BuffRemovalReason.EXPLICIT,
            )
        )
    return tuple(removals)


def _enemy_positions(context: Any) -> tuple[tuple[str, Any], ...]:
    """返回当前全部敌人的空间实体 id 与位置；缺少投影的敌人被忽略。"""

    positions: list[tuple[str, Any]] = []
    for target in context.space_runtime.targets.targets:
        entity = context.space_runtime.get_entity(target.spatial_entity_id)
        if entity is None:
            continue
        positions.append((target.spatial_entity_id, entity.position))
    return tuple(positions)
