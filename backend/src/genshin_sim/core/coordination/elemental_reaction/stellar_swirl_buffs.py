"""辉映·星扩散 Buff 的跨系统计划。

该模块是星扩散写协调的 Buff 侧窄入口：只依据星扩散·风触发的 occurrence
与 capability 资格证据，生成确定性的 Buff 申请，不拥有长期状态。
辉映·星扩散 Buff 与辉映·星超导 Buff 可同时存在，Buff 层不做跨
Definition 互斥；同时满足两种辉映条件时的生效优先级由角色侧读取逻辑承担。
"""

from __future__ import annotations

from collections.abc import Sequence

from genshin_sim.core.attributes import (
    STELLAR_SWIRL_DIRECT_BASE_MULTIPLIER,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffModifierValue,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_TEAM_SCOPE,
    STELLAR_SWIRL_VORTEX_SCOPE,
)

STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY = "buff.reaction.stellar_swirl.radiance"
STELLAR_SWIRL_RADIANCE_BUFF_MECHANIC_KEY = "reaction.stellar_swirl"
STELLAR_SWIRL_RADIANCE_BUFF_HANDLER_KEY = "reaction_handler.stellar_swirl.radiance"
STELLAR_SWIRL_RADIANCE_BUFF_CONFLICT_KEY = "buff_conflict.reaction.stellar_swirl.radiance"
STELLAR_SWIRL_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY = "stellar.swirl.radiance.direct_base_multiplier"
# 辉映·星扩散 Buff 的存续基线（约 8 秒，480 帧）；精确帧边界待来源化冻结。
STELLAR_SWIRL_RADIANCE_DURATION_FRAMES = 480
# 直伤星烁基础系数证据固定为 1，具体倍率由角色侧能力与公式承担。
STELLAR_SWIRL_RADIANCE_DIRECT_MULTIPLIER_VALUE = 1.0

# 风旋爆炸命中角色后的跳跃能力 Buff。
STELLAR_SWIRL_JUMP_BOOST_BUFF_DEFINITION_KEY = "buff.reaction.stellar_swirl.jump_boost"
STELLAR_SWIRL_JUMP_BOOST_BUFF_MECHANIC_KEY = "reaction.stellar_swirl"
STELLAR_SWIRL_JUMP_BOOST_BUFF_HANDLER_KEY = "reaction_handler.stellar_swirl.jump_boost"
STELLAR_SWIRL_JUMP_BOOST_BUFF_CONFLICT_KEY = "buff_conflict.reaction.stellar_swirl.jump_boost"
# 跳跃能力 Buff 的存续基线（约 6 秒，360 帧）。精确帧边界与"跳跃能力"的量化
# 口径均待来源化冻结；Movement 尚无跳跃能力模型，因此不声明属性词条。
STELLAR_SWIRL_JUMP_BOOST_DURATION_FRAMES = 360


def stellar_swirl_radiance_buff_definition() -> BuffDefinition:
    """辉映·星扩散 Buff：星扩散·风触发的角色侧投影，携带直伤系数证据。"""

    return BuffDefinition(
        definition_key=STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY,
        mechanic_key=STELLAR_SWIRL_RADIANCE_BUFF_MECHANIC_KEY,
        handler_key=STELLAR_SWIRL_RADIANCE_BUFF_HANDLER_KEY,
        conflict_key=STELLAR_SWIRL_RADIANCE_BUFF_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=STELLAR_SWIRL_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY,
                target_key=STELLAR_SWIRL_DIRECT_BASE_MULTIPLIER,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({STELLAR_SWIRL_RADIANCE_BUFF_MECHANIC_KEY}),
        display_name="辉映·星扩散",
    )


def plan_stellar_swirl_radiance_buff_requests(
    *,
    frame: int,
    occurrence_ref: str,
    character_refs: Sequence[AttributeSubjectRef],
    order_start: int = 0,
) -> tuple[ApplyBuffRequest, ...]:
    """为具备辉映·星扩散资格的角色生成统一刷新的 Buff 申请。

    每次星扩散·风触发后按固定基线 ``STELLAR_SWIRL_RADIANCE_DURATION_FRAMES``
    申请或刷新；多次触发按 ``REFRESH`` 顺延，词条数值固定为 ``1.0``。
    """

    source_context = RuntimeSourceRef(
        RuntimeSourceKind.MECHANIC,
        STELLAR_SWIRL_RADIANCE_BUFF_MECHANIC_KEY,
        STELLAR_SWIRL_VORTEX_SCOPE,
    )
    ordered_refs = sorted(character_refs, key=lambda item: item.entity_id)
    return tuple(
        ApplyBuffRequest(
            request_id=f"{occurrence_ref}:stellar-swirl-radiance:{ref.entity_id}",
            frame=frame,
            order=order_start + order,
            definition_key=STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY,
            target_ref=ref,
            source_context=source_context,
            duration_frames=STELLAR_SWIRL_RADIANCE_DURATION_FRAMES,
            modifier_values=(
                BuffModifierValue(
                    STELLAR_SWIRL_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY,
                    STELLAR_SWIRL_RADIANCE_DIRECT_MULTIPLIER_VALUE,
                ),
            ),
        )
        for order, ref in enumerate(ordered_refs)
    )


def stellar_swirl_jump_boost_buff_definition() -> BuffDefinition:
    """星辉风旋爆炸命中角色的跳跃能力 Buff：位置级队伍作用域挂载。

    挂载在 ``ACTIVE_CHARACTER`` 位置级主体上：跳跃只有前台角色能执行，谁在
    前台谁享受，切人后由新前台自然接管。Movement 尚无跳跃能力模型，因此 Buff
    为 ``marker_only``，不声明任何属性词条；"完成一次跳跃后消失"由 Movement
    起跳事实触发的 ``CONSUMED`` 显式移除承担，不新增生命周期状态。
    """

    return BuffDefinition(
        definition_key=STELLAR_SWIRL_JUMP_BOOST_BUFF_DEFINITION_KEY,
        mechanic_key=STELLAR_SWIRL_JUMP_BOOST_BUFF_MECHANIC_KEY,
        handler_key=STELLAR_SWIRL_JUMP_BOOST_BUFF_HANDLER_KEY,
        conflict_key=STELLAR_SWIRL_JUMP_BOOST_BUFF_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.ACTIVE_CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        marker_only=True,
        tags=frozenset({STELLAR_SWIRL_JUMP_BOOST_BUFF_MECHANIC_KEY}),
        display_name="星辉风旋·跳跃能力",
    )


def plan_stellar_swirl_jump_boost_request(
    *,
    frame: int,
    effect_group_ref: str,
    team_ref: str = STELLAR_SWIRL_TEAM_SCOPE,
    order: int = 0,
) -> ApplyBuffRequest:
    """为爆炸命中的前台角色生成一条位置级跳跃能力 Buff 申请。

    爆炸不是反应、没有 occurrence，因果锚点是爆炸 Effect group 本身：以它
    作为申请 id 前缀既能表达归属，也比复用上游 occurrence 更不易撞号。
    位置级主体只有一条记录：同帧多次命中或多次爆炸按 ``REFRESH`` 顺延，
    不按命中角色数复制。``source_context`` 与辉映·星扩散 Buff 一致，保证
    同一主体上的刷新兼容。
    """

    return ApplyBuffRequest(
        request_id=f"{effect_group_ref}:stellar-swirl-jump-boost",
        frame=frame,
        order=order,
        definition_key=STELLAR_SWIRL_JUMP_BOOST_BUFF_DEFINITION_KEY,
        target_ref=AttributeSubjectRef.active_character(team_ref),
        source_context=RuntimeSourceRef(
            RuntimeSourceKind.MECHANIC,
            STELLAR_SWIRL_JUMP_BOOST_BUFF_MECHANIC_KEY,
            STELLAR_SWIRL_VORTEX_SCOPE,
        ),
        duration_frames=STELLAR_SWIRL_JUMP_BOOST_DURATION_FRAMES,
        modifier_values=(),
    )
