"""ReactionStatusEffect 到 Buff 的显式适配器。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.attributes import (
    RESISTANCE_PHYSICAL,
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
from genshin_sim.core.systems.reaction import ReactionStatusEffect

SUPERCONDUCT_STATUS_PROFILE_KEY = (
    "reaction_status_profile.superconduct.physical_resistance_reduction"
)
SUPERCONDUCT_BUFF_DEFINITION_KEY = "buff.reaction.superconduct.physical_resistance_reduction"
SUPERCONDUCT_STATUS_HANDLER_KEY = (
    "reaction_status_handler.superconduct.physical_resistance_reduction"
)
SUPERCONDUCT_BUFF_CONFLICT_KEY = "buff_conflict.reaction.superconduct.physical_resistance_reduction"
SUPERCONDUCT_BUFF_TERM_KEY = "resistance.physical.reduction"


def superconduct_buff_definition() -> BuffDefinition:
    return BuffDefinition(
        definition_key=SUPERCONDUCT_BUFF_DEFINITION_KEY,
        mechanic_key="reaction.superconduct",
        handler_key=SUPERCONDUCT_STATUS_HANDLER_KEY,
        conflict_key=SUPERCONDUCT_BUFF_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.TARGET}),
        application_policy=BuffApplicationPolicy.REPLACE,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=SUPERCONDUCT_BUFF_TERM_KEY,
                target_key=RESISTANCE_PHYSICAL,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({"reaction.superconduct"}),
    )


@dataclass(frozen=True, slots=True)
class ReactionStatusBuffAdapter:
    """只映射已经冻结的超导物理减抗状态。"""

    def to_request(
        self,
        effect: ReactionStatusEffect,
        *,
        frame: int,
        target_ref: AttributeSubjectRef,
        target_order: int,
    ) -> ApplyBuffRequest:
        if effect.status_profile_key != SUPERCONDUCT_STATUS_PROFILE_KEY:
            raise ValueError(f"未注册的 ReactionStatusEffect adapter：{effect.status_profile_key}")
        source_ref = effect.parent_occurrence_ref
        if source_ref is None:
            cause = effect.cause
            source_ref = getattr(cause, "cause_ref", None)
        if not isinstance(source_ref, str) or not source_ref.strip():
            raise ValueError("Reaction Status Effect 缺少可审计来源 cause")
        return ApplyBuffRequest(
            request_id=f"{effect.effect_ref}:target:{target_order}:buff",
            frame=frame,
            order=target_order,
            definition_key=SUPERCONDUCT_BUFF_DEFINITION_KEY,
            target_ref=target_ref,
            source_context=RuntimeSourceRef(
                RuntimeSourceKind.MECHANIC,
                effect.status_profile_key,
                source_ref,
            ),
            duration_frames=effect.duration_frames,
            modifier_values=(BuffModifierValue(SUPERCONDUCT_BUFF_TERM_KEY, effect.value),),
        )
